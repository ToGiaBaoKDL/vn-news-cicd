from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts.services.polaris.config import (
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


def runtime_cli(config: PolarisDeployConfig, credentials: PolarisCredentials) -> PolarisCli:
    return PolarisCli(base_url=config.base_url, credentials=credentials)
