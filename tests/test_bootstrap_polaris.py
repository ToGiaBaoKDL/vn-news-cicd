from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
import pytest
from news_platform.contracts.tables import CURATED_TABLE_CONTRACTS, NEWS_ARTICLE_VERSION
from scripts.services.polaris import (
    bootstrap_catalog,
    catalog,
    provision_access,
)
from scripts.services.polaris import (
    client as polaris_client,
)
from scripts.services.polaris import (
    validate_access as validate_polaris_access_script,
)


def catalog_config() -> polaris_client.PolarisCatalogConfig:
    return polaris_client.PolarisCatalogConfig(
        management_url="http://polaris:8181/api/management/v1",
        catalog_url="http://polaris:8181/api/catalog",
        catalog_name="vn_news",
        warehouse_uri="s3://curated-bucket/warehouse",
        storage_endpoint_url="http://seaweedfs:8333",
        storage_endpoint_internal_url=None,
        storage_sts_endpoint_url=None,
        storage_role_arn=None,
        storage_user_arn=None,
        storage_external_id=None,
        storage_region="us-east-1",
        oauth_scope=polaris_client.DEFAULT_OAUTH_SCOPE,
        timeout_seconds=30.0,
    )


def bootstrap_credentials() -> polaris_client.PolarisCredentials:
    return polaris_client.PolarisCredentials(
        realm="POLARIS",
        client_id="admin",
        client_secret="secret",
    )


def access_config(tmp_path: Path | None = None) -> provision_access.PolarisAccessConfig:
    return provision_access.PolarisAccessConfig(
        principal_name="vn-news-spark-runtime",
        principal_role_name="vn-news-spark-runtime",
        catalog_role_name="vn-news-curated-writer",
        credentials_output_file=(tmp_path / "polaris-client-credentials.json")
        if tmp_path
        else None,
        rotate_credentials=False,
    )


def token_response(request: httpx.Request) -> httpx.Response:
    assert request.headers["Polaris-Realm"] == "POLARIS"
    assert request.headers["authorization"].startswith("Basic ")
    assert b"grant_type=client_credentials" in request.content
    assert b"scope=PRINCIPAL_ROLE%3AALL" in request.content
    return httpx.Response(200, json={"access_token": "token"}, request=request)


def test_load_bootstrap_credentials_reads_single_realm_file(tmp_path: Path) -> None:
    credentials_file = tmp_path / "polaris-bootstrap-credentials.json"
    credentials_file.write_text(
        json.dumps({"POLARIS": {"client-id": "admin", "client-secret": "secret"}}),
        encoding="utf-8",
    )

    credentials = polaris_client.load_bootstrap_credentials(credentials_file)

    assert credentials == bootstrap_credentials()


def test_create_table_request_is_derived_from_contract() -> None:
    partition = NEWS_ARTICLE_VERSION.partition_fields()[0]
    assert (partition.transform, partition.field_name, partition.name) == (
        "day",
        "ingest_date",
        "ingest_date_day",
    )

    request = catalog.create_table_request(
        NEWS_ARTICLE_VERSION,
        "s3://curated-bucket/warehouse",
    )

    assert request["name"] == NEWS_ARTICLE_VERSION.name
    assert request["location"] == "s3://curated-bucket/warehouse/curated/news_article_version"
    assert request["properties"] == dict(NEWS_ARTICLE_VERSION.properties)
    assert request["schema"]["type"] == "struct"
    assert [field["id"] for field in request["schema"]["fields"]] == list(
        range(1, len(NEWS_ARTICLE_VERSION.fields) + 1)
    )
    assert request["schema"]["fields"][0] == {
        "id": 1,
        "name": "article_id",
        "type": "string",
        "required": True,
    }
    assert request["partition-spec"]["fields"] == [
        {
            "field-id": 1000,
            "source-id": 15,
            "name": "ingest_date_day",
            "transform": "day",
        }
    ]


def test_all_curated_table_requests_use_contract_names() -> None:
    table_requests = [
        catalog.create_table_request(contract, "s3://curated-bucket/warehouse")
        for contract in CURATED_TABLE_CONTRACTS
    ]

    assert [request["name"] for request in table_requests] == [
        contract.name for contract in CURATED_TABLE_CONTRACTS
    ]
    assert len({request["location"] for request in table_requests}) == len(CURATED_TABLE_CONTRACTS)


def test_management_url_can_be_derived_from_catalog_url() -> None:
    assert (
        polaris_client.derive_management_url("http://polaris:8181/api/catalog")
        == "http://polaris:8181/api/management/v1"
    )


def test_build_config_uses_lakehouse_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        polaris_client,
        "load_settings",
        lambda: {
            "storage": {
                "endpoint_url": "http://seaweedfs:8333",
                "buckets": {"curated": "curated-bucket"},
            },
            "lakehouse": {"catalog_name": "vn_news", "warehouse_prefix": "warehouse"},
        },
    )

    args = argparse.Namespace(
        catalog_url="http://polaris:8181/api/catalog",
        management_url=None,
        catalog_name=None,
        storage_endpoint_url=None,
        storage_endpoint_internal_url=None,
        storage_sts_endpoint_url=None,
        storage_role_arn=None,
        storage_user_arn=None,
        storage_external_id=None,
        storage_region="us-east-1",
        warehouse_uri=None,
        oauth_scope=polaris_client.DEFAULT_OAUTH_SCOPE,
        timeout_seconds=30.0,
    )

    config = polaris_client.build_catalog_config(args)

    assert config.catalog_name == "vn_news"
    assert config.management_url == "http://polaris:8181/api/management/v1"
    assert config.warehouse_uri == "s3://curated-bucket/warehouse"


def test_pending_runtime_credentials_force_rotation(tmp_path: Path) -> None:
    current_credentials_file = tmp_path / "polaris-client-credentials.current.json"
    current_credentials_file.write_text(
        json.dumps({"status": polaris_client.PENDING_RUNTIME_CREDENTIALS_STATUS}),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        runtime_principal_name="vn-news-spark-runtime",
        runtime_principal_role_name="vn-news-spark-runtime",
        runtime_catalog_role_name="vn-news-curated-writer",
        runtime_credentials_output_file=tmp_path / "polaris-client-credentials.new.json",
        current_runtime_credentials_file=current_credentials_file,
        rotate_runtime_credentials=False,
    )

    config = provision_access.build_access_config(args)

    assert config.rotate_credentials is True


def test_bootstrapper_creates_catalog_namespace_and_tables() -> None:
    requests: list[httpx.Request] = []
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.headers.get("content-type") == "application/json" and request.content:
            payloads.append(json.loads(request.content.decode()))
        if request.url.path == "/api/catalog/v1/oauth/tokens":
            return token_response(request)
        if request.method == "GET":
            return httpx.Response(404, request=request)
        return httpx.Response(201, json={}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        bootstrap_catalog.PolarisCatalogBootstrapper(
            client,
            catalog_config(),
            bootstrap_credentials(),
        ).bootstrap_catalog((NEWS_ARTICLE_VERSION,))

    assert requests[0].method == "POST"
    assert requests[0].url.path == "/api/catalog/v1/oauth/tokens"
    catalog_payload = payloads[0]
    assert catalog_payload["catalog"]["storageConfigInfo"]["endpoint"] == "http://seaweedfs:8333"
    assert "stsUnavailable" not in catalog_payload["catalog"]["storageConfigInfo"]
    assert (
        catalog.create_table_request(
            NEWS_ARTICLE_VERSION,
            "s3://curated-bucket/warehouse",
        )
        in payloads
    )


def test_provisioner_creates_runtime_principal_roles_and_grants(tmp_path: Path) -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("content-type") == "application/json" and request.content:
            payloads.append(json.loads(request.content.decode()))
        if request.url.path == "/api/catalog/v1/oauth/tokens":
            return token_response(request)
        if request.method == "GET" and request.url.path.endswith("/principal-roles"):
            return httpx.Response(200, json={"roles": []}, request=request)
        if (
            request.method == "GET"
            and request.url.path
            == "/api/management/v1/principal-roles/vn-news-spark-runtime/catalog-roles/vn_news"
        ):
            return httpx.Response(200, json={"roles": []}, request=request)
        if request.method == "GET" and request.url.path.endswith("/grants"):
            return httpx.Response(200, json={"grants": []}, request=request)
        if request.method == "GET":
            return httpx.Response(404, request=request)
        if request.method == "POST" and request.url.path == "/api/management/v1/principals":
            return httpx.Response(
                201,
                json={
                    "principal": {"name": "vn-news-spark-runtime"},
                    "credentials": {
                        "clientId": "runtime-client",
                        "clientSecret": "runtime-secret",
                    },
                },
                request=request,
            )
        return httpx.Response(201, json={}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provisioner = provision_access.PolarisAccessProvisioner(
            client,
            catalog_config(),
            bootstrap_credentials(),
            access_config(tmp_path),
        )
        credentials = provisioner.provision_access((NEWS_ARTICLE_VERSION,))

    assert credentials == polaris_client.PolarisCredentials(
        realm="POLARIS",
        client_id="runtime-client",
        client_secret="runtime-secret",
    )
    assert any(
        payload.get("principal", {}).get("name") == "vn-news-spark-runtime" for payload in payloads
    )
    assert any(
        payload.get("principalRole", {}).get("name") == "vn-news-spark-runtime"
        for payload in payloads
    )
    assert any(
        payload.get("catalogRole", {}).get("name") == "vn-news-curated-writer"
        for payload in payloads
    )
    assert {
        "grant": {
            "type": "table",
            "namespace": ["curated"],
            "tableName": "news_article_version",
            "privilege": "TABLE_WRITE_DATA",
        }
    } in payloads


def test_validator_requires_vended_credentials() -> None:
    requests: list[httpx.Request] = []

    def vended_credentials_payload() -> dict[str, object]:
        return {
            "storage-credentials": [
                {
                    "prefix": "s3://curated-bucket/warehouse",
                    "config": {
                        "s3.access-key-id": "access",
                        "s3.secret-access-key": "secret",
                    },
                }
            ]
        }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/catalog/v1/oauth/tokens":
            return token_response(request)
        if request.method == "GET" and request.url.path.endswith("/credentials"):
            return httpx.Response(200, json=vended_credentials_payload(), request=request)
        if request.method == "GET" and request.url.path.endswith("/tables/news_article_version"):
            return httpx.Response(200, json=vended_credentials_payload(), request=request)
        return httpx.Response(404, request=request)

    runtime_credentials = polaris_client.PolarisCredentials(
        realm="POLARIS",
        client_id="runtime-client",
        client_secret="secret",
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        validate_polaris_access_script.PolarisAccessValidator(
            client,
            catalog_config(),
            runtime_credentials,
        ).validate_credential_vending(runtime_credentials, NEWS_ARTICLE_VERSION)

    table_load_request = next(
        request
        for request in requests
        if request.url.path.endswith("/tables/news_article_version")
        and not request.url.path.endswith("/credentials")
    )
    assert table_load_request.headers["X-Iceberg-Access-Delegation"] == "vended-credentials"


def test_existing_table_schema_drift_is_rejected() -> None:
    payload = {
        "metadata": {
            "location": "s3://curated-bucket/warehouse/curated/news_article_version",
            "current-schema-id": 0,
            "schemas": [{"schema-id": 0, "type": "struct", "fields": []}],
            "default-spec-id": 0,
            "partition-specs": [{"spec-id": 0, "fields": []}],
        }
    }

    with pytest.raises(ValueError, match="curated.news_article_version drift"):
        catalog.validate_existing_table(
            payload,
            NEWS_ARTICLE_VERSION,
            "s3://curated-bucket/warehouse",
        )
