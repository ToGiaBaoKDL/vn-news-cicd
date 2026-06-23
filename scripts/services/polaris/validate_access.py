from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import httpx
from news_platform.contracts.tables import CURATED_TABLE_CONTRACTS, IcebergTableContract

from scripts.services.polaris.catalog import table_catalog_url
from scripts.services.polaris.client import (
    PolarisCatalogConfig,
    PolarisClient,
    PolarisCredentials,
    add_catalog_arguments,
    build_catalog_config,
    join_url,
    load_runtime_credentials,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Polaris runtime access.")
    add_catalog_arguments(parser)
    parser.add_argument(
        "--runtime-credentials-file",
        type=Path,
        required=True,
    )
    return parser.parse_args()


def validate_vended_credentials(payload: dict[str, Any], label: str) -> None:
    storage_credentials = payload.get("storage-credentials")
    if not isinstance(storage_credentials, list) or not storage_credentials:
        raise ValueError(f"{label} did not return storage-credentials")
    if not any(
        isinstance(credential, dict)
        and isinstance(credential.get("prefix"), str)
        and isinstance(credential.get("config"), dict)
        and credential["config"]
        for credential in storage_credentials
    ):
        raise ValueError(f"{label} returned malformed storage-credentials")


class PolarisAccessValidator(PolarisClient):
    def validate_table_access(
        self,
        runtime_credentials: PolarisCredentials,
        contract: IcebergTableContract,
    ) -> None:
        token = self.request_access_token(runtime_credentials)
        headers = self.auth_headers_for(runtime_credentials, token)
        table_url = table_catalog_url(self.config.catalog_url, self.config.catalog_name, contract)
        response = self.client.get(table_url, headers=headers)
        response.raise_for_status()
        print(f"validated Polaris table access: {contract.identifier}")

    def validate_credential_vending(
        self,
        runtime_credentials: PolarisCredentials,
        contract: IcebergTableContract,
    ) -> None:
        token = self.request_access_token(runtime_credentials)
        headers = self.auth_headers_for(runtime_credentials, token)
        table_url = table_catalog_url(self.config.catalog_url, self.config.catalog_name, contract)

        table_response = self.client.get(
            table_url,
            headers={**headers, "X-Iceberg-Access-Delegation": "vended-credentials"},
        )
        table_response.raise_for_status()
        validate_vended_credentials(
            table_response.json(),
            f"Polaris table load for {contract.identifier}",
        )

        credentials_response = self.client.get(join_url(table_url, "credentials"), headers=headers)
        credentials_response.raise_for_status()
        validate_vended_credentials(
            credentials_response.json(),
            f"Polaris credentials load for {contract.identifier}",
        )
        print(f"validated Polaris credential vending: {contract.identifier}")


def main() -> None:
    args = parse_args()
    config: PolarisCatalogConfig = build_catalog_config(args)
    runtime_credentials = load_runtime_credentials(args.runtime_credentials_file)
    with httpx.Client(timeout=config.timeout_seconds) as client:
        validator = PolarisAccessValidator(client, config, runtime_credentials)
        if config.storage_sts_unavailable:
            validator.validate_table_access(runtime_credentials, CURATED_TABLE_CONTRACTS[0])
        else:
            validator.validate_credential_vending(runtime_credentials, CURATED_TABLE_CONTRACTS[0])


if __name__ == "__main__":
    main()
