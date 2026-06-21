from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from news_platform.contracts.tables import CURATED_TABLE_CONTRACTS, IcebergTableContract

from scripts.services.polaris.client import (
    PolarisCatalogConfig,
    PolarisClient,
    PolarisCredentials,
    add_bootstrap_credentials_argument,
    add_catalog_arguments,
    build_catalog_config,
    encode_path_part,
    join_url,
    load_bootstrap_credentials,
    namespace_parts,
    runtime_credentials_are_pending,
    write_credentials_file,
)

DEFAULT_RUNTIME_CATALOG_ROLE_NAME = "vn-news-curated-writer"
DEFAULT_RUNTIME_PRINCIPAL_NAME = "vn-news-spark-runtime"
DEFAULT_RUNTIME_PRINCIPAL_ROLE_NAME = "vn-news-spark-runtime"

RUNTIME_NAMESPACE_PRIVILEGES = (
    "NAMESPACE_READ_PROPERTIES",
    "TABLE_LIST",
)

RUNTIME_TABLE_PRIVILEGES = (
    "TABLE_READ_PROPERTIES",
    "TABLE_READ_DATA",
    "TABLE_WRITE_DATA",
    "TABLE_FULL_METADATA",
    "TABLE_ADD_SNAPSHOT",
)


@dataclass(frozen=True)
class PolarisAccessConfig:
    principal_name: str
    principal_role_name: str
    catalog_role_name: str
    credentials_output_file: Path | None
    rotate_credentials: bool


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_entity_name(value: str | None, name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{name} is required")
    stripped = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", stripped):
        raise ValueError(f"{name} must contain only letters, numbers, dot, underscore, or hyphen")
    if stripped.lower() == "system":
        raise ValueError(f"{name} must not be system")
    return stripped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision Polaris runtime access.")
    add_catalog_arguments(parser)
    add_bootstrap_credentials_argument(parser)
    parser.add_argument(
        "--runtime-principal-name",
        default=os.environ.get(
            "VN_NEWS_POLARIS_RUNTIME_PRINCIPAL_NAME",
            DEFAULT_RUNTIME_PRINCIPAL_NAME,
        ),
    )
    parser.add_argument(
        "--runtime-principal-role-name",
        default=os.environ.get(
            "VN_NEWS_POLARIS_RUNTIME_PRINCIPAL_ROLE_NAME",
            DEFAULT_RUNTIME_PRINCIPAL_ROLE_NAME,
        ),
    )
    parser.add_argument(
        "--runtime-catalog-role-name",
        default=os.environ.get(
            "VN_NEWS_POLARIS_RUNTIME_CATALOG_ROLE_NAME",
            DEFAULT_RUNTIME_CATALOG_ROLE_NAME,
        ),
    )
    parser.add_argument(
        "--runtime-credentials-output-file",
        type=Path,
        default=(
            Path(os.environ["VN_NEWS_POLARIS_RUNTIME_CREDENTIALS_OUTPUT_FILE"])
            if os.environ.get("VN_NEWS_POLARIS_RUNTIME_CREDENTIALS_OUTPUT_FILE")
            else None
        ),
    )
    parser.add_argument(
        "--current-runtime-credentials-file",
        type=Path,
        default=(
            Path(os.environ["VN_NEWS_POLARIS_CURRENT_RUNTIME_CREDENTIALS_FILE"])
            if os.environ.get("VN_NEWS_POLARIS_CURRENT_RUNTIME_CREDENTIALS_FILE")
            else None
        ),
    )
    parser.add_argument(
        "--rotate-runtime-credentials",
        action="store_true",
        default=env_bool("VN_NEWS_POLARIS_ROTATE_RUNTIME_CREDENTIALS"),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def build_access_config(args: argparse.Namespace) -> PolarisAccessConfig:
    return PolarisAccessConfig(
        principal_name=normalize_entity_name(args.runtime_principal_name, "runtime principal name"),
        principal_role_name=normalize_entity_name(
            args.runtime_principal_role_name,
            "runtime principal role name",
        ),
        catalog_role_name=normalize_entity_name(
            args.runtime_catalog_role_name, "runtime role name"
        ),
        credentials_output_file=args.runtime_credentials_output_file,
        rotate_credentials=args.rotate_runtime_credentials
        or runtime_credentials_are_pending(args.current_runtime_credentials_file),
    )


def credentials_from_principal_response(payload: dict[str, Any], realm: str) -> PolarisCredentials:
    credentials = payload.get("credentials")
    if not isinstance(credentials, dict):
        raise ValueError("Polaris principal response missing credentials")
    client_id = credentials.get("clientId")
    client_secret = credentials.get("clientSecret")
    if not isinstance(client_id, str) or not client_id:
        raise ValueError("Polaris principal response missing clientId")
    if not isinstance(client_secret, str) or not client_secret:
        raise ValueError("Polaris principal response missing clientSecret")
    return PolarisCredentials(realm=realm, client_id=client_id, client_secret=client_secret)


def grant_key(grant: dict[str, Any]) -> str:
    return json.dumps(grant, sort_keys=True, separators=(",", ":"))


def runtime_grants(contracts: tuple[IcebergTableContract, ...]) -> tuple[dict[str, Any], ...]:
    grants: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append(grant: dict[str, Any]) -> None:
        key = grant_key(grant)
        if key not in seen:
            seen.add(key)
            grants.append(grant)

    for namespace in sorted({contract.namespace for contract in contracts}):
        for privilege in RUNTIME_NAMESPACE_PRIVILEGES:
            append(
                {
                    "type": "namespace",
                    "namespace": namespace_parts(namespace),
                    "privilege": privilege,
                }
            )

    for contract in contracts:
        for privilege in RUNTIME_TABLE_PRIVILEGES:
            append(
                {
                    "type": "table",
                    "namespace": namespace_parts(contract.namespace),
                    "tableName": contract.name,
                    "privilege": privilege,
                }
            )

    return tuple(grants)


class PolarisAccessProvisioner(PolarisClient):
    def __init__(
        self,
        client: httpx.Client,
        catalog_config: PolarisCatalogConfig,
        credentials: PolarisCredentials,
        access_config: PolarisAccessConfig,
    ) -> None:
        super().__init__(client, catalog_config, credentials)
        self.access_config = access_config

    def ensure_runtime_principal(self) -> PolarisCredentials | None:
        principal_name = self.access_config.principal_name
        principal_url = join_url(
            self.config.management_url,
            "principals",
            encode_path_part(principal_name),
        )
        response = self.client.get(principal_url, headers=self.auth_headers())
        if response.status_code == 200:
            print(f"exists Polaris runtime principal: {principal_name}")
            if not self.access_config.rotate_credentials:
                return None
            rotate_response = self.client.post(
                join_url(principal_url, "rotate"),
                headers=self.auth_headers(),
            )
            rotate_response.raise_for_status()
            print(f"rotated Polaris runtime credentials: {principal_name}")
            return credentials_from_principal_response(
                rotate_response.json(),
                self.credentials.realm,
            )
        if response.status_code != 404:
            response.raise_for_status()

        create_response = self.client.post(
            join_url(self.config.management_url, "principals"),
            headers=self.auth_headers(),
            json={
                "principal": {
                    "name": principal_name,
                    "properties": {
                        "managed-by": "vn-news-cicd",
                        "purpose": "spark-curated-writer",
                    },
                },
                "credentialRotationRequired": False,
            },
        )
        if create_response.status_code == 409:
            print(f"exists Polaris runtime principal: {principal_name}")
            return None
        create_response.raise_for_status()
        print(f"created Polaris runtime principal: {principal_name}")
        return credentials_from_principal_response(create_response.json(), self.credentials.realm)

    def ensure_principal_role(self) -> None:
        role_name = self.access_config.principal_role_name
        role_url = join_url(
            self.config.management_url,
            "principal-roles",
            encode_path_part(role_name),
        )
        response = self.client.get(role_url, headers=self.auth_headers())
        if response.status_code == 200:
            print(f"exists Polaris principal role: {role_name}")
            return
        if response.status_code != 404:
            response.raise_for_status()

        create_response = self.client.post(
            join_url(self.config.management_url, "principal-roles"),
            headers=self.auth_headers(),
            json={
                "principalRole": {
                    "name": role_name,
                    "properties": {
                        "managed-by": "vn-news-cicd",
                        "purpose": "spark-curated-writer",
                    },
                }
            },
        )
        if create_response.status_code == 409:
            print(f"exists Polaris principal role: {role_name}")
            return
        create_response.raise_for_status()
        print(f"created Polaris principal role: {role_name}")

    def assign_principal_role(self) -> None:
        principal_name = self.access_config.principal_name
        role_name = self.access_config.principal_role_name
        roles_url = join_url(
            self.config.management_url,
            "principals",
            encode_path_part(principal_name),
            "principal-roles",
        )
        response = self.client.get(roles_url, headers=self.auth_headers())
        response.raise_for_status()
        roles = response.json().get("roles", [])
        if any(role.get("name") == role_name for role in roles if isinstance(role, dict)):
            print(f"exists Polaris principal role assignment: {principal_name} -> {role_name}")
            return

        assign_response = self.client.put(
            roles_url,
            headers=self.auth_headers(),
            json={"principalRole": {"name": role_name}},
        )
        assign_response.raise_for_status()
        print(f"assigned Polaris principal role: {principal_name} -> {role_name}")

    def ensure_catalog_role(self) -> None:
        role_name = self.access_config.catalog_role_name
        role_url = join_url(
            self.config.management_url,
            "catalogs",
            encode_path_part(self.config.catalog_name),
            "catalog-roles",
            encode_path_part(role_name),
        )
        response = self.client.get(role_url, headers=self.auth_headers())
        if response.status_code == 200:
            print(f"exists Polaris catalog role: {self.config.catalog_name}/{role_name}")
            return
        if response.status_code != 404:
            response.raise_for_status()

        create_response = self.client.post(
            join_url(
                self.config.management_url,
                "catalogs",
                encode_path_part(self.config.catalog_name),
                "catalog-roles",
            ),
            headers=self.auth_headers(),
            json={
                "catalogRole": {
                    "name": role_name,
                    "properties": {
                        "managed-by": "vn-news-cicd",
                        "purpose": "spark-curated-writer",
                    },
                }
            },
        )
        if create_response.status_code == 409:
            print(f"exists Polaris catalog role: {self.config.catalog_name}/{role_name}")
            return
        create_response.raise_for_status()
        print(f"created Polaris catalog role: {self.config.catalog_name}/{role_name}")

    def assign_catalog_role(self) -> None:
        principal_role_name = self.access_config.principal_role_name
        catalog_role_name = self.access_config.catalog_role_name
        roles_url = join_url(
            self.config.management_url,
            "principal-roles",
            encode_path_part(principal_role_name),
            "catalog-roles",
            encode_path_part(self.config.catalog_name),
        )
        response = self.client.get(roles_url, headers=self.auth_headers())
        response.raise_for_status()
        roles = response.json().get("roles", [])
        if any(role.get("name") == catalog_role_name for role in roles if isinstance(role, dict)):
            print(
                "exists Polaris catalog role assignment: "
                f"{principal_role_name} -> {self.config.catalog_name}/{catalog_role_name}"
            )
            return

        assign_response = self.client.put(
            roles_url,
            headers=self.auth_headers(),
            json={"catalogRole": {"name": catalog_role_name}},
        )
        assign_response.raise_for_status()
        print(
            "assigned Polaris catalog role: "
            f"{principal_role_name} -> {self.config.catalog_name}/{catalog_role_name}"
        )

    def ensure_grants(self, contracts: tuple[IcebergTableContract, ...]) -> None:
        grants_url = join_url(
            self.config.management_url,
            "catalogs",
            encode_path_part(self.config.catalog_name),
            "catalog-roles",
            encode_path_part(self.access_config.catalog_role_name),
            "grants",
        )
        response = self.client.get(grants_url, headers=self.auth_headers())
        response.raise_for_status()
        existing = {
            grant_key(grant)
            for grant in response.json().get("grants", [])
            if isinstance(grant, dict)
        }

        for grant in runtime_grants(contracts):
            if grant_key(grant) in existing:
                continue
            add_response = self.client.put(
                grants_url,
                headers=self.auth_headers(),
                json={"grant": grant},
            )
            add_response.raise_for_status()
            print(f"granted Polaris runtime privilege: {grant}")

    def provision_access(
        self,
        contracts: tuple[IcebergTableContract, ...],
    ) -> PolarisCredentials | None:
        self.authenticate()
        new_credentials = self.ensure_runtime_principal()
        self.ensure_principal_role()
        self.assign_principal_role()
        self.ensure_catalog_role()
        self.assign_catalog_role()
        self.ensure_grants(contracts)
        return new_credentials


def print_dry_run(
    catalog_config: PolarisCatalogConfig,
    access_config: PolarisAccessConfig,
) -> None:
    print(f"would ensure Polaris runtime principal: {access_config.principal_name}")
    print(f"would ensure Polaris principal role: {access_config.principal_role_name}")
    print(
        "would ensure Polaris catalog role: "
        f"{catalog_config.catalog_name}/{access_config.catalog_role_name}"
    )
    for grant in runtime_grants(CURATED_TABLE_CONTRACTS):
        print(f"would ensure Polaris runtime grant: {grant}")


def main() -> None:
    args = parse_args()
    catalog_config = build_catalog_config(args)
    access_config = build_access_config(args)
    if args.dry_run:
        print_dry_run(catalog_config, access_config)
        return

    credentials = load_bootstrap_credentials(args.credentials_file)
    with httpx.Client(timeout=catalog_config.timeout_seconds) as client:
        provisioner = PolarisAccessProvisioner(client, catalog_config, credentials, access_config)
        new_credentials = provisioner.provision_access(CURATED_TABLE_CONTRACTS)

    if new_credentials is None:
        return
    if access_config.credentials_output_file is None:
        raise RuntimeError(
            "Runtime credentials were created or rotated, but "
            "--runtime-credentials-output-file was not provided"
        )
    write_credentials_file(access_config.credentials_output_file, new_credentials)


if __name__ == "__main__":
    main()
