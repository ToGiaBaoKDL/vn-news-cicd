from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts.services.polaris.config import (
    LEGACY_RUNTIME_CATALOG_ROLE_NAMES,
    RUNTIME_ENTITY_PROPERTIES,
    PolarisCredentials,
    PolarisDeployConfig,
    credentials_from_cli_payload,
)


@dataclass(frozen=True)
class PolarisCli:
    base_url: str
    credentials: PolarisCredentials
    polaris_bin: str = "polaris"

    def command(self, *args: str) -> list[str]:
        return [
            self.polaris_bin,
            "--base-url",
            self.base_url,
            "--client-id",
            self.credentials.client_id,
            "--client-secret",
            self.credentials.client_secret,
            "--realm",
            self.credentials.realm,
            "--header",
            "Polaris-Realm",
            *args,
        ]

    def run(
        self,
        *args: str,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.command(*args),
            check=check,
            capture_output=capture_output,
            text=True,
        )

    def run_json(self, *args: str) -> dict:
        result = self.run(*args, capture_output=True)
        return json.loads(result.stdout)

    def resource_exists(self, *args: str) -> bool:
        result = self.run(*args, check=False, capture_output=True)
        if result.returncode == 0:
            return True
        output = f"{result.stdout}\n{result.stderr}".lower()
        if "404" in output or "not found" in output:
            return False
        result.check_returncode()
        return False

    def setup_apply(self, path: Path, *, dry_run: bool = False) -> None:
        args = ["setup", "apply", str(path)]
        if dry_run:
            args.append("--dry-run")
        self.run(*args)

    def create_runtime_principal(
        self,
        config: PolarisDeployConfig,
    ) -> PolarisCredentials | None:
        principal_name = config.runtime_principal_name
        if self.resource_exists("principals", "get", principal_name):
            print(f"exists Polaris runtime principal: {principal_name}")
            return None

        result = self.run(
            "principals",
            "create",
            "--type",
            "service",
            "--property",
            f"managed-by={RUNTIME_ENTITY_PROPERTIES['managed-by']}",
            "--property",
            f"purpose={RUNTIME_ENTITY_PROPERTIES['purpose']}",
            principal_name,
            capture_output=True,
        )
        print(f"created Polaris runtime principal: {principal_name}")
        return credentials_from_cli_payload(result.stdout, self.credentials.realm)

    def rotate_runtime_credentials(self, config: PolarisDeployConfig) -> PolarisCredentials:
        result = self.run(
            "principals",
            "rotate-credentials",
            config.runtime_principal_name,
            capture_output=True,
        )
        print(f"rotated Polaris runtime credentials: {config.runtime_principal_name}")
        return credentials_from_cli_payload(result.stdout, self.credentials.realm)

    def cleanup_legacy_catalog_roles(self, config: PolarisDeployConfig) -> None:
        for role_name in LEGACY_RUNTIME_CATALOG_ROLE_NAMES:
            if not self.resource_exists(
                "catalog-roles",
                "get",
                "--catalog",
                config.catalog_name,
                role_name,
            ):
                continue

            role = self.run_json(
                "catalog-roles",
                "get",
                "--catalog",
                config.catalog_name,
                role_name,
            )
            role_payload = role.get("catalogRole", role) if isinstance(role, dict) else {}
            properties = (
                role_payload.get("properties", {}) if isinstance(role_payload, dict) else {}
            )
            if properties.get("managed-by") != RUNTIME_ENTITY_PROPERTIES["managed-by"]:
                raise RuntimeError(
                    "Refusing to delete unmanaged legacy Polaris catalog role: "
                    f"{config.catalog_name}/{role_name}"
                )

            self.run(
                "catalog-roles",
                "revoke",
                "--catalog",
                config.catalog_name,
                "--principal-role",
                config.runtime_principal_role_name,
                role_name,
                check=False,
                capture_output=True,
            )
            self.run("catalog-roles", "delete", "--catalog", config.catalog_name, role_name)
            print(f"removed legacy Polaris catalog role: {config.catalog_name}/{role_name}")


def runtime_cli(config: PolarisDeployConfig, credentials: PolarisCredentials) -> PolarisCli:
    return PolarisCli(base_url=config.base_url, credentials=credentials)
