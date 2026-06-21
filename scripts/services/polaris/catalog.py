from __future__ import annotations

from typing import Any

from news_platform.contracts.tables import IcebergTableContract

from scripts.services.polaris.client import (
    PolarisCatalogConfig,
    encode_namespace,
    encode_path_part,
    join_url,
    namespace_parts,
)

ICEBERG_TYPE_BY_CONTRACT_TYPE = {
    "date": "date",
    "int": "int",
    "long": "long",
    "string": "string",
    "timestamp": "timestamp",
}


def table_location(warehouse_uri: str, contract: IcebergTableContract) -> str:
    namespace_path = "/".join(namespace_parts(contract.namespace))
    return f"{warehouse_uri.rstrip('/')}/{namespace_path}/{contract.name}"


def table_catalog_url(
    catalog_url: str,
    catalog_name: str,
    contract: IcebergTableContract,
) -> str:
    return join_url(
        catalog_url,
        "v1",
        encode_path_part(catalog_name),
        "namespaces",
        encode_namespace(contract.namespace),
        "tables",
        encode_path_part(contract.name),
    )


def iceberg_type(contract_type: str) -> str:
    try:
        return ICEBERG_TYPE_BY_CONTRACT_TYPE[contract_type]
    except KeyError as error:
        raise ValueError(f"Unsupported Iceberg contract type: {contract_type}") from error


def iceberg_schema(contract: IcebergTableContract) -> dict[str, Any]:
    fields = []
    for field_id, field in enumerate(contract.fields, start=1):
        field_payload: dict[str, Any] = {
            "id": field_id,
            "name": field.name,
            "type": iceberg_type(field.data_type),
            "required": field.required,
        }
        if field.description:
            field_payload["doc"] = field.description
        fields.append(field_payload)
    return {"type": "struct", "fields": fields}


def iceberg_partition_spec(contract: IcebergTableContract) -> dict[str, Any]:
    field_ids = {field.name: field_id for field_id, field in enumerate(contract.fields, start=1)}
    partition_fields = []
    for offset, partition in enumerate(contract.partition_fields()):
        try:
            source_id = field_ids[partition.field_name]
        except KeyError as error:
            raise ValueError(
                f"{contract.identifier} partitions by unknown field: {partition.field_name}"
            ) from error
        partition_fields.append(
            {
                "field-id": 1000 + offset,
                "source-id": source_id,
                "name": partition.name,
                "transform": partition.transform,
            }
        )
    return {"fields": partition_fields}


def create_table_request(contract: IcebergTableContract, warehouse_uri: str) -> dict[str, Any]:
    return {
        "name": contract.name,
        "location": table_location(warehouse_uri, contract),
        "schema": iceberg_schema(contract),
        "partition-spec": iceberg_partition_spec(contract),
        "stage-create": False,
        "properties": dict(contract.properties),
    }


def create_catalog_request(config: PolarisCatalogConfig) -> dict[str, Any]:
    storage_config: dict[str, Any] = {
        "storageType": "S3",
        "allowedLocations": [config.warehouse_uri],
        "endpoint": config.storage_endpoint_url,
        "pathStyleAccess": True,
        "region": config.storage_region,
    }
    optional_storage_fields = {
        "endpointInternal": config.storage_endpoint_internal_url,
        "stsEndpoint": config.storage_sts_endpoint_url,
        "roleArn": config.storage_role_arn,
        "userArn": config.storage_user_arn,
        "externalId": config.storage_external_id,
    }
    storage_config.update(
        {key: value for key, value in optional_storage_fields.items() if value is not None}
    )
    return {
        "catalog": {
            "type": "INTERNAL",
            "name": config.catalog_name,
            "properties": {"default-base-location": config.warehouse_uri},
            "storageConfigInfo": storage_config,
        }
    }


def current_schema(metadata: dict[str, Any]) -> dict[str, Any] | None:
    schemas = metadata.get("schemas")
    if not isinstance(schemas, list):
        schema = metadata.get("schema")
        return schema if isinstance(schema, dict) else None

    current_schema_id = metadata.get("current-schema-id")
    for schema in schemas:
        if schema.get("schema-id") == current_schema_id:
            return schema
    return schemas[-1] if schemas else None


def current_partition_spec(metadata: dict[str, Any]) -> dict[str, Any] | None:
    partition_specs = metadata.get("partition-specs")
    if not isinstance(partition_specs, list):
        partition_spec = metadata.get("partition-spec")
        return partition_spec if isinstance(partition_spec, dict) else None

    default_spec_id = metadata.get("default-spec-id")
    for spec in partition_specs:
        if spec.get("spec-id") == default_spec_id:
            return spec
    return partition_specs[-1] if partition_specs else None


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} drift: expected {expected!r}, got {actual!r}")


def validate_existing_catalog(catalog: dict[str, Any], config: PolarisCatalogConfig) -> None:
    require_equal(catalog.get("type"), "INTERNAL", "Polaris catalog type")
    require_equal(
        catalog.get("properties", {}).get("default-base-location"),
        config.warehouse_uri,
        "Polaris catalog warehouse",
    )
    storage_config = catalog.get("storageConfigInfo", {})
    require_equal(storage_config.get("storageType"), "S3", "Polaris catalog storage type")
    require_equal(
        storage_config.get("endpoint"),
        config.storage_endpoint_url,
        "Polaris S3 endpoint",
    )
    require_equal(storage_config.get("pathStyleAccess"), True, "Polaris S3 path-style access")
    if storage_config.get("stsUnavailable") is True:
        raise ValueError("Polaris catalog disables credential vending with stsUnavailable=true")
    allowed_locations = storage_config.get("allowedLocations") or []
    if config.warehouse_uri not in allowed_locations:
        raise ValueError(
            "Polaris catalog allowed locations drift: "
            f"expected {config.warehouse_uri!r} in {allowed_locations!r}"
        )
    optional_storage_fields = {
        "endpointInternal": config.storage_endpoint_internal_url,
        "stsEndpoint": config.storage_sts_endpoint_url,
        "roleArn": config.storage_role_arn,
        "userArn": config.storage_user_arn,
        "externalId": config.storage_external_id,
    }
    for field_name, expected in optional_storage_fields.items():
        if expected is not None:
            require_equal(storage_config.get(field_name), expected, f"Polaris S3 {field_name}")


def validate_existing_table(
    payload: dict[str, Any],
    contract: IcebergTableContract,
    warehouse_uri: str,
) -> None:
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError(f"{contract.identifier} load result missing Iceberg metadata")

    if metadata.get("location"):
        require_equal(
            metadata["location"],
            table_location(warehouse_uri, contract),
            contract.identifier,
        )

    schema = current_schema(metadata)
    if schema is None:
        raise ValueError(f"{contract.identifier} metadata missing current schema")
    require_equal(schema.get("fields", []), iceberg_schema(contract)["fields"], contract.identifier)

    partition_spec = current_partition_spec(metadata)
    actual_partition_fields = partition_spec.get("fields", []) if partition_spec else []
    expected_partition_fields = iceberg_partition_spec(contract)["fields"]
    require_equal(actual_partition_fields, expected_partition_fields, contract.identifier)
