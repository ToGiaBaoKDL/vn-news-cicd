from __future__ import annotations

import argparse

import httpx
from news_platform.contracts.tables import CURATED_TABLE_CONTRACTS, IcebergTableContract

from scripts.services.polaris.catalog import (
    create_catalog_request,
    create_table_request,
    validate_existing_catalog,
    validate_existing_table,
)
from scripts.services.polaris.client import (
    PolarisCatalogConfig,
    PolarisClient,
    add_bootstrap_credentials_argument,
    add_catalog_arguments,
    build_catalog_config,
    encode_namespace,
    encode_path_part,
    join_url,
    load_bootstrap_credentials,
    namespace_parts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap the Polaris curated Iceberg catalog.")
    add_catalog_arguments(parser)
    add_bootstrap_credentials_argument(parser)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


class PolarisCatalogBootstrapper(PolarisClient):
    def ensure_catalog(self) -> None:
        catalog_url = join_url(
            self.config.management_url,
            "catalogs",
            encode_path_part(self.config.catalog_name),
        )
        response = self.client.get(catalog_url, headers=self.auth_headers())
        if response.status_code == 200:
            validate_existing_catalog(response.json(), self.config)
            print(f"exists Polaris catalog: {self.config.catalog_name}")
            return
        if response.status_code != 404:
            response.raise_for_status()

        create_response = self.client.post(
            join_url(self.config.management_url, "catalogs"),
            headers=self.auth_headers(),
            json=create_catalog_request(self.config),
        )
        if create_response.status_code == 409:
            response = self.client.get(catalog_url, headers=self.auth_headers())
            response.raise_for_status()
            validate_existing_catalog(response.json(), self.config)
            print(f"exists Polaris catalog: {self.config.catalog_name}")
            return
        create_response.raise_for_status()
        print(f"created Polaris catalog: {self.config.catalog_name}")

    def ensure_namespace(self, namespace: str) -> None:
        namespace_url = join_url(
            self.config.catalog_url,
            "v1",
            encode_path_part(self.config.catalog_name),
            "namespaces",
            encode_namespace(namespace),
        )
        response = self.client.get(namespace_url, headers=self.auth_headers())
        if response.status_code == 200:
            print(f"exists Iceberg namespace: {namespace}")
            return
        if response.status_code != 404:
            response.raise_for_status()

        create_response = self.client.post(
            join_url(
                self.config.catalog_url,
                "v1",
                encode_path_part(self.config.catalog_name),
                "namespaces",
            ),
            headers=self.auth_headers(),
            json={"namespace": namespace_parts(namespace), "properties": {}},
        )
        if create_response.status_code == 409:
            print(f"exists Iceberg namespace: {namespace}")
            return
        create_response.raise_for_status()
        print(f"created Iceberg namespace: {namespace}")

    def ensure_table(self, contract: IcebergTableContract) -> None:
        table_url = join_url(
            self.config.catalog_url,
            "v1",
            encode_path_part(self.config.catalog_name),
            "namespaces",
            encode_namespace(contract.namespace),
            "tables",
            encode_path_part(contract.name),
        )
        response = self.client.get(table_url, headers=self.auth_headers())
        if response.status_code == 200:
            validate_existing_table(response.json(), contract, self.config.warehouse_uri)
            print(f"exists Iceberg table: {contract.identifier}")
            return
        if response.status_code != 404:
            response.raise_for_status()

        create_response = self.client.post(
            join_url(
                self.config.catalog_url,
                "v1",
                encode_path_part(self.config.catalog_name),
                "namespaces",
                encode_namespace(contract.namespace),
                "tables",
            ),
            headers=self.auth_headers(),
            json=create_table_request(contract, self.config.warehouse_uri),
        )
        if create_response.status_code == 409:
            response = self.client.get(table_url, headers=self.auth_headers())
            response.raise_for_status()
            validate_existing_table(response.json(), contract, self.config.warehouse_uri)
            print(f"exists Iceberg table: {contract.identifier}")
            return
        create_response.raise_for_status()
        print(f"created Iceberg table: {contract.identifier}")

    def bootstrap_catalog(self, contracts: tuple[IcebergTableContract, ...]) -> None:
        self.authenticate()
        self.ensure_catalog()
        for namespace in sorted({contract.namespace for contract in contracts}):
            self.ensure_namespace(namespace)
        for contract in contracts:
            self.ensure_table(contract)


def print_dry_run(config: PolarisCatalogConfig) -> None:
    print(f"would request Polaris token: {join_url(config.catalog_url, 'v1', 'oauth', 'tokens')}")
    print(f"would ensure Polaris catalog: {config.catalog_name}")
    print(f"  warehouse: {config.warehouse_uri}")
    print(f"  storage endpoint: {config.storage_endpoint_url}")
    for namespace in sorted({contract.namespace for contract in CURATED_TABLE_CONTRACTS}):
        print(f"would ensure Iceberg namespace: {namespace}")
    for contract in CURATED_TABLE_CONTRACTS:
        print(f"would ensure Iceberg table: {contract.identifier}")


def main() -> None:
    args = parse_args()
    config = build_catalog_config(args)
    if args.dry_run:
        print_dry_run(config)
        return

    credentials = load_bootstrap_credentials(args.credentials_file)
    with httpx.Client(timeout=config.timeout_seconds) as client:
        PolarisCatalogBootstrapper(client, config, credentials).bootstrap_catalog(
            CURATED_TABLE_CONTRACTS
        )


if __name__ == "__main__":
    main()
