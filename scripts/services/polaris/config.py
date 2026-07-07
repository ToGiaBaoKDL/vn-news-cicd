from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from news_platform.config import (
    get_lakehouse_catalog_name,
    get_lakehouse_warehouse_uri,
    load_settings,
)
from news_platform.contracts.tables import CURATED_TABLE_CONTRACTS

DEFAULT_OAUTH_SCOPE = "PRINCIPAL_ROLE:ALL"
DEFAULT_STORAGE_REGION = "us-east-1"
DEFAULT_RUNTIME_CATALOG_ROLE_NAME = "vn-news-spark-runtime-writer"
DEFAULT_RUNTIME_PRINCIPAL_NAME = "vn-news-spark-runtime"
DEFAULT_RUNTIME_PRINCIPAL_ROLE_NAME = "vn-news-spark-runtime"
LEGACY_RUNTIME_CATALOG_ROLE_NAMES = ("vn-news-curated-writer",)
PENDING_RUNTIME_CREDENTIALS_STATUS = "pending-polaris-runtime-principal"
RUNTIME_ENTITY_PROPERTIES = {
    "managed-by": "vn-news-cicd",
    "purpose": "spark-runtime-writer",
}
RUNTIME_NAMESPACE_PRIVILEGES = (
    "NAMESPACE_READ_PROPERTIES",
    "TABLE_LIST",
    "TABLE_CREATE",
    "TABLE_READ_PROPERTIES",
    "TABLE_READ_DATA",
    "TABLE_WRITE_DATA",
    "TABLE_FULL_METADATA",
    "TABLE_ADD_SNAPSHOT",
)


@dataclass(frozen=True)
class PolarisCredentials:
    realm: str
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class PolarisDeployConfig:
    base_url: str
    catalog_name: str
    warehouse_uri: str
    storage_endpoint_url: str
    storage_endpoint_internal_url: str | None
    storage_sts_endpoint_url: str | None
    storage_sts_unavailable: bool
    storage_role_arn: str | None
    storage_user_arn: str | None
    storage_external_id: str | None
    storage_region: str
    runtime_principal_name: str
    runtime_principal_role_name: str
    runtime_catalog_role_name: str
    runtime_namespaces: tuple[str, ...]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def default_secrets_dir() -> Path:
    return Path(os.environ.get("VN_NEWS_SECRETS_HOST_DIR", "/run/vn-news/secrets"))


def normalize_entity_name(value: str | None, name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{name} is required")
    stripped = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", stripped):
        raise ValueError(f"{name} must contain only letters, numbers, dot, underscore, or hyphen")
    if stripped.lower() == "system":
        raise ValueError(f"{name} must not be system")
    return stripped


def normalize_url(url: str | None, name: str) -> str:
    if not url or not url.strip():
        raise ValueError(f"{name} is required")
    return url.rstrip("/")


def derive_polaris_base_url(catalog_url: str) -> str:
    normalized = normalize_url(catalog_url, "Polaris catalog URL")
    for suffix in ("/api/catalog/v1", "/api/catalog"):
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    raise ValueError("Polaris catalog URL must end with /api/catalog or /api/catalog/v1")


def add_deploy_config_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--catalog-url", default=os.environ.get("VN_NEWS_POLARIS_CATALOG_URL"))
    parser.add_argument("--base-url", default=os.environ.get("VN_NEWS_POLARIS_BASE_URL"))
    parser.add_argument("--catalog-name", default=os.environ.get("VN_NEWS_POLARIS_CATALOG_NAME"))
    parser.add_argument("--warehouse-uri", default=os.environ.get("VN_NEWS_POLARIS_WAREHOUSE_URI"))
    parser.add_argument(
        "--storage-endpoint-url",
        default=os.environ.get("VN_NEWS_STORAGE_ENDPOINT_URL"),
    )
    parser.add_argument(
        "--storage-endpoint-internal-url",
        default=os.environ.get("VN_NEWS_POLARIS_STORAGE_ENDPOINT_INTERNAL_URL"),
    )
    parser.add_argument(
        "--storage-sts-endpoint-url",
        default=os.environ.get("VN_NEWS_POLARIS_STORAGE_STS_ENDPOINT_URL"),
    )
    parser.add_argument(
        "--storage-sts-unavailable",
        action=argparse.BooleanOptionalAction,
        default=env_bool("VN_NEWS_POLARIS_STORAGE_STS_UNAVAILABLE"),
    )
    parser.add_argument(
        "--storage-role-arn",
        default=os.environ.get("VN_NEWS_POLARIS_STORAGE_ROLE_ARN"),
    )
    parser.add_argument(
        "--storage-user-arn",
        default=os.environ.get("VN_NEWS_POLARIS_STORAGE_USER_ARN"),
    )
    parser.add_argument(
        "--storage-external-id",
        default=os.environ.get("VN_NEWS_POLARIS_STORAGE_EXTERNAL_ID"),
    )
    parser.add_argument(
        "--storage-region",
        default=os.environ.get("VN_NEWS_POLARIS_STORAGE_REGION", DEFAULT_STORAGE_REGION),
    )
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


def add_bootstrap_credentials_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--credentials-file",
        type=Path,
        default=default_secrets_dir() / "polaris-bootstrap-credentials.json",
    )


def build_deploy_config(args: argparse.Namespace) -> PolarisDeployConfig:
    settings = load_settings()
    catalog_url = normalize_url(args.catalog_url, "Polaris catalog URL")
    base_url = normalize_url(args.base_url, "Polaris base URL") if args.base_url else ""
    storage_endpoint_url = args.storage_endpoint_url or settings["storage"]["endpoint_url"]
    catalog_name = args.catalog_name or get_lakehouse_catalog_name(settings)
    warehouse_uri = (args.warehouse_uri or get_lakehouse_warehouse_uri(settings)).rstrip("/")
    runtime_namespaces = tuple(sorted({contract.namespace for contract in CURATED_TABLE_CONTRACTS}))

    return PolarisDeployConfig(
        base_url=base_url or derive_polaris_base_url(catalog_url),
        catalog_name=normalize_entity_name(catalog_name, "catalog name"),
        warehouse_uri=warehouse_uri,
        storage_endpoint_url=normalize_url(storage_endpoint_url, "storage endpoint URL"),
        storage_endpoint_internal_url=(
            normalize_url(args.storage_endpoint_internal_url, "internal storage endpoint URL")
            if args.storage_endpoint_internal_url
            else None
        ),
        storage_sts_endpoint_url=(
            normalize_url(args.storage_sts_endpoint_url, "storage STS endpoint URL")
            if args.storage_sts_endpoint_url
            else None
        ),
        storage_sts_unavailable=args.storage_sts_unavailable,
        storage_role_arn=args.storage_role_arn or None,
        storage_user_arn=args.storage_user_arn or None,
        storage_external_id=args.storage_external_id or None,
        storage_region=args.storage_region,
        runtime_principal_name=normalize_entity_name(
            args.runtime_principal_name,
            "runtime principal name",
        ),
        runtime_principal_role_name=normalize_entity_name(
            args.runtime_principal_role_name,
            "runtime principal role name",
        ),
        runtime_catalog_role_name=normalize_entity_name(
            args.runtime_catalog_role_name,
            "runtime catalog role name",
        ),
        runtime_namespaces=runtime_namespaces,
    )


def parse_credentials_payload(payload: dict[str, Any], label: str) -> PolarisCredentials:
    if len(payload) != 1:
        raise ValueError(f"{label} must contain exactly one realm")

    realm, credentials = next(iter(payload.items()))
    if not isinstance(credentials, dict):
        raise ValueError(f"{label} for realm {realm} must be an object")

    client_id = credentials.get("client-id")
    client_secret = credentials.get("client-secret")
    if not isinstance(client_id, str) or not client_id:
        raise ValueError(f"{label} for realm {realm} missing client-id")
    if not isinstance(client_secret, str) or not client_secret:
        raise ValueError(f"{label} for realm {realm} missing client-secret")
    return PolarisCredentials(realm=realm, client_id=client_id, client_secret=client_secret)


def load_credentials(path: Path, label: str) -> PolarisCredentials:
    return parse_credentials_payload(json.loads(path.read_text(encoding="utf-8")), label)


def credentials_payload(credentials: PolarisCredentials) -> dict[str, dict[str, str]]:
    return {
        credentials.realm: {
            "client-id": credentials.client_id,
            "client-secret": credentials.client_secret,
        }
    }


def credentials_from_cli_payload(payload: str, realm: str) -> PolarisCredentials:
    parsed = json.loads(payload)
    client_id = parsed.get("clientId")
    client_secret = parsed.get("clientSecret")
    if not isinstance(client_id, str) or not client_id:
        raise ValueError("Polaris CLI response missing clientId")
    if not isinstance(client_secret, str) or not client_secret:
        raise ValueError("Polaris CLI response missing clientSecret")
    return PolarisCredentials(realm=realm, client_id=client_id, client_secret=client_secret)


def runtime_credentials_are_pending(content: str) -> bool:
    return json.loads(content).get("status") == PENDING_RUNTIME_CREDENTIALS_STATUS


def render_runtime_setup_config(config: PolarisDeployConfig) -> dict[str, Any]:
    storage_config: dict[str, Any] = {
        "name": config.catalog_name,
        "type": "internal",
        "storage_type": "s3",
        "default_base_location": config.warehouse_uri,
        "allowed_locations": [config.warehouse_uri],
        "endpoint": config.storage_endpoint_url,
        "path_style_access": True,
        "region": config.storage_region,
        "sts_unavailable": config.storage_sts_unavailable,
        "namespaces": list(config.runtime_namespaces),
        "roles": {
            config.runtime_catalog_role_name: {
                "properties": RUNTIME_ENTITY_PROPERTIES,
                "assign_to": [config.runtime_principal_role_name],
                "privileges": {
                    "namespace": {
                        namespace: list(RUNTIME_NAMESPACE_PRIVILEGES)
                        for namespace in config.runtime_namespaces
                    }
                },
            }
        },
    }
    optional_storage_fields = {
        "endpoint_internal": config.storage_endpoint_internal_url,
        "sts_endpoint": config.storage_sts_endpoint_url,
        "role_arn": config.storage_role_arn,
        "user_arn": config.storage_user_arn,
        "external_id": config.storage_external_id,
    }
    storage_config.update(
        {key: value for key, value in optional_storage_fields.items() if value is not None}
    )
    return {
        "principal_roles": [config.runtime_principal_role_name],
        "principals": {
            config.runtime_principal_name: {
                "type": "service",
                "properties": RUNTIME_ENTITY_PROPERTIES,
                "roles": [config.runtime_principal_role_name],
            }
        },
        "catalogs": [storage_config],
    }


def write_setup_config(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
