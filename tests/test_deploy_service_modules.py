from __future__ import annotations

import argparse
from pathlib import Path

from scripts.services.airflow import validate_dag
from scripts.services.polaris import vault
from scripts.services.spark import validate_cluster


def test_redpanda_provisioning_uses_service_container_rpk() -> None:
    deploy_script = Path("scripts/deploy/services/redpanda.sh").read_text(encoding="utf-8")

    assert "exec -T redpanda rpk" in deploy_script
    assert "--brokers localhost:9092" in deploy_script
    assert "docker run --rm --entrypoint rpk" not in deploy_script


def test_airflow_dag_validation_handles_prefixed_logs() -> None:
    output = 'loading config\n[{"dag_id":"vn_news_hourly_ingestion"}]\n'

    assert validate_dag.has_dag(output, "vn_news_hourly_ingestion")
    assert not validate_dag.has_dag(output, "missing_dag")


def test_spark_worker_validation_requires_alive_worker_host() -> None:
    payload = {
        "workers": [
            {"host": "10.0.10.31", "state": "DEAD"},
            {"host": "10.0.10.32", "state": "ALIVE"},
        ]
    }

    assert validate_cluster.worker_is_alive(payload, "10.0.10.32")
    assert not validate_cluster.worker_is_alive(payload, "10.0.10.31")
    assert not validate_cluster.worker_is_alive(payload, "10.0.10.33")


def test_polaris_vault_uses_instance_principal_by_default() -> None:
    args = argparse.Namespace(oci_bin="oci", oci_auth="instance_principal")

    assert vault.oci_command(args, "secrets", "secret-bundle", "get") == [
        "oci",
        "secrets",
        "secret-bundle",
        "get",
        "--auth",
        "instance_principal",
    ]


def test_polaris_vault_allows_default_oci_profile() -> None:
    args = argparse.Namespace(oci_bin="oci", oci_auth="default")

    assert vault.oci_command(args, "vault", "secret", "update-base64") == [
        "oci",
        "vault",
        "secret",
        "update-base64",
    ]
