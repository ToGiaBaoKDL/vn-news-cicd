from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pytest
from scripts.services.polaris import config as polaris_config
from scripts.services.polaris import provision
from scripts.services.polaris.cli import PolarisCli


def test_load_credentials_reads_single_realm_file(tmp_path: Path) -> None:
    credentials_file = tmp_path / "polaris-bootstrap-credentials.json"
    credentials_file.write_text(
        json.dumps({"POLARIS": {"client-id": "admin", "client-secret": "secret"}}),
        encoding="utf-8",
    )

    credentials = polaris_config.load_credentials(credentials_file, "bootstrap")

    assert credentials == polaris_config.PolarisCredentials(
        realm="POLARIS",
        client_id="admin",
        client_secret="secret",
    )


def test_polaris_base_url_is_derived_from_catalog_url() -> None:
    assert (
        polaris_config.derive_polaris_base_url("http://polaris:8181/api/catalog")
        == "http://polaris:8181"
    )
    assert (
        polaris_config.derive_polaris_base_url("http://polaris:8181/api/catalog/v1")
        == "http://polaris:8181"
    )


def test_render_runtime_setup_config_uses_official_setup_schema() -> None:
    deploy_config = polaris_config.PolarisDeployConfig(
        base_url="http://polaris:8181",
        catalog_name="vn_news",
        warehouse_uri="s3://curated-bucket/warehouse",
        storage_endpoint_url="http://seaweedfs:8333",
        storage_endpoint_internal_url="http://seaweedfs-s3:8333",
        storage_sts_endpoint_url=None,
        storage_sts_unavailable=True,
        storage_role_arn=None,
        storage_user_arn=None,
        storage_external_id=None,
        storage_region="us-east-1",
        runtime_principal_name="vn-news-spark-runtime",
        runtime_principal_role_name="vn-news-spark-runtime",
        runtime_catalog_role_name="vn-news-spark-runtime-writer",
        runtime_namespaces=("curated",),
    )

    payload = polaris_config.render_runtime_setup_config(deploy_config)

    assert payload["principal_roles"] == ["vn-news-spark-runtime"]
    assert payload["principals"]["vn-news-spark-runtime"]["roles"] == ["vn-news-spark-runtime"]
    catalog = payload["catalogs"][0]
    assert catalog["name"] == "vn_news"
    assert catalog["storage_type"] == "s3"
    assert catalog["default_base_location"] == "s3://curated-bucket/warehouse"
    assert catalog["endpoint_internal"] == "http://seaweedfs-s3:8333"
    assert catalog["roles"]["vn-news-spark-runtime-writer"]["assign_to"] == [
        "vn-news-spark-runtime"
    ]
    assert (
        "TABLE_CREATE"
        in catalog["roles"]["vn-news-spark-runtime-writer"]["privileges"]["namespace"]["curated"]
    )
    assert "tables" not in catalog


def test_pending_runtime_credentials_are_detected() -> None:
    assert polaris_config.runtime_credentials_are_pending(
        json.dumps({"status": polaris_config.PENDING_RUNTIME_CREDENTIALS_STATUS})
    )
    assert not polaris_config.runtime_credentials_are_pending(
        json.dumps({"POLARIS": {"client-id": "runtime", "client-secret": "secret"}})
    )


def test_cli_command_uses_official_polaris_binary_and_realm_header() -> None:
    cli = PolarisCli(
        base_url="http://polaris:8181",
        credentials=polaris_config.PolarisCredentials(
            realm="POLARIS",
            client_id="admin",
            client_secret="secret",
        ),
    )

    assert cli.command("catalogs", "list") == [
        "polaris",
        "--base-url",
        "http://polaris:8181",
        "--client-id",
        "admin",
        "--client-secret",
        "secret",
        "--realm",
        "POLARIS",
        "--header",
        "Polaris-Realm",
        "catalogs",
        "list",
    ]


def test_cli_create_runtime_principal_parses_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    deploy_config = polaris_config.PolarisDeployConfig(
        base_url="http://polaris:8181",
        catalog_name="vn_news",
        warehouse_uri="s3://curated-bucket/warehouse",
        storage_endpoint_url="http://seaweedfs:8333",
        storage_endpoint_internal_url=None,
        storage_sts_endpoint_url=None,
        storage_sts_unavailable=True,
        storage_role_arn=None,
        storage_user_arn=None,
        storage_external_id=None,
        storage_region="us-east-1",
        runtime_principal_name="vn-news-spark-runtime",
        runtime_principal_role_name="vn-news-spark-runtime",
        runtime_catalog_role_name="vn-news-spark-runtime-writer",
        runtime_namespaces=("curated",),
    )
    calls: list[list[str]] = []

    def fake_run(command, check, capture_output, text):
        calls.append(command)
        if command[-3:] == ["principals", "get", "vn-news-spark-runtime"]:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"clientId": "runtime-client", "clientSecret": "runtime-secret"}),
            "",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    cli = PolarisCli(
        base_url="http://polaris:8181",
        credentials=polaris_config.PolarisCredentials("POLARIS", "admin", "secret"),
    )

    credentials = cli.create_runtime_principal(deploy_config)

    assert credentials == polaris_config.PolarisCredentials(
        realm="POLARIS",
        client_id="runtime-client",
        client_secret="runtime-secret",
    )
    assert any("principals" in call for call in calls)


def test_provision_updates_vault_when_runtime_secret_is_pending(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    credentials_file = tmp_path / "bootstrap.json"
    credentials_file.write_text(
        json.dumps({"POLARIS": {"client-id": "admin", "client-secret": "secret"}}),
        encoding="utf-8",
    )
    updates: list[str] = []
    applied_setup_files: list[Path] = []

    deploy_config = polaris_config.PolarisDeployConfig(
        base_url="http://polaris:8181",
        catalog_name="vn_news",
        warehouse_uri="s3://curated-bucket/warehouse",
        storage_endpoint_url="http://seaweedfs:8333",
        storage_endpoint_internal_url=None,
        storage_sts_endpoint_url=None,
        storage_sts_unavailable=True,
        storage_role_arn=None,
        storage_user_arn=None,
        storage_external_id=None,
        storage_region="us-east-1",
        runtime_principal_name="vn-news-spark-runtime",
        runtime_principal_role_name="vn-news-spark-runtime",
        runtime_catalog_role_name="vn-news-spark-runtime-writer",
        runtime_namespaces=("curated",),
    )

    monkeypatch.setattr(provision, "build_deploy_config", lambda args: deploy_config)
    monkeypatch.setattr(
        provision,
        "read_secret",
        lambda args, secret_id: json.dumps(
            {"status": polaris_config.PENDING_RUNTIME_CREDENTIALS_STATUS}
        ),
    )
    monkeypatch.setattr(
        provision,
        "update_secret",
        lambda args, secret_id, content, content_name: updates.append(content),
    )
    monkeypatch.setattr(
        PolarisCli,
        "resource_exists",
        lambda self, *args: args[-1] == "vn-news-spark-runtime",
    )
    monkeypatch.setattr(
        PolarisCli,
        "rotate_runtime_credentials",
        lambda self, config: polaris_config.PolarisCredentials(
            "POLARIS",
            "runtime-client",
            "runtime-secret",
        ),
    )
    monkeypatch.setattr(
        PolarisCli,
        "setup_apply",
        lambda self, path, dry_run=False: applied_setup_files.append(Path(path)),
    )
    monkeypatch.setattr(PolarisCli, "cleanup_legacy_catalog_roles", lambda self, config: None)

    args = argparse.Namespace(
        credentials_file=credentials_file,
        runtime_credentials_secret_id="secret-ocid",
        rotate_runtime_credentials=False,
        dry_run=False,
        oci_bin="oci",
        oci_auth="instance_principal",
    )

    provision.provision(args)

    assert json.loads(updates[0]) == {
        "POLARIS": {
            "client-id": "runtime-client",
            "client-secret": "runtime-secret",
        }
    }
    assert applied_setup_files
