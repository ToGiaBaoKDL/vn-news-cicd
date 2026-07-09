from __future__ import annotations

from pathlib import Path

from scripts.workspace.common import CICD_ROOT, INFRA_ROOT

REQUIRED_SCRIPT_FILES = (
    "scripts/deploy/remote_node.sh",
    "scripts/deploy/refs.py",
    "scripts/images/artifacts.py",
    "scripts/images/build.py",
    "scripts/images/catalog.py",
    "scripts/images/changed.py",
    "scripts/images/digests.py",
    "scripts/images/imagetools.py",
    "scripts/images/manifest.py",
    "scripts/images/promote.py",
    "scripts/images/tags.py",
    "scripts/images/verify.py",
    "scripts/services/polaris/cli.py",
    "scripts/services/polaris/config.py",
    "scripts/services/polaris/provision.py",
    "scripts/services/polaris/validate.py",
    "scripts/services/polaris/vault.py",
    "scripts/services/redpanda/provision_schema_registry.py",
    "scripts/services/redpanda/provision_topics.py",
    "scripts/services/redpanda/register_schemas.py",
    "scripts/services/redpanda/rpk.py",
    "scripts/services/seaweedfs/provision_buckets.py",
    "scripts/services/spark/validate_cluster.py",
    "scripts/workspace/common.py",
    "scripts/workspace/deploy_contracts.py",
    "scripts/workspace/env_contracts.py",
    "scripts/workspace/image_contracts.py",
    "scripts/workspace/repo_layout.py",
    "scripts/workspace/settings_contracts.py",
    "scripts/workspace/verify.py",
    "scripts/workspace/workflow_contracts.py",
)
REQUIRED_DEPLOY_SERVICE_FILES = (
    "scripts/deploy/services/airflow.sh",
    "scripts/deploy/services/app.sh",
    "scripts/deploy/services/cloudflare.sh",
    "scripts/deploy/services/ingestion.sh",
    "scripts/deploy/services/polaris.sh",
    "scripts/deploy/services/redpanda.sh",
    "scripts/deploy/services/seaweedfs.sh",
    "scripts/deploy/services/spark.sh",
)
REQUIRED_INFRA_DEPLOY_FILES = (
    "scripts/host/bootstrap.sh",
    "scripts/host/configure_operations.sh",
    "scripts/host/reset_role.sh",
    "scripts/lib/common.sh",
    "scripts/lib/firewall.sh",
    "scripts/lib/oci.sh",
    "scripts/resource_manager/job.sh",
    "scripts/secrets/materialize.sh",
)


def validate_script_layout() -> None:
    missing_scripts = [path for path in REQUIRED_SCRIPT_FILES if not (CICD_ROOT / path).is_file()]
    if missing_scripts:
        raise ValueError(f"Missing modular CICD script files: {missing_scripts}")

    missing_deploy_services = [
        path for path in REQUIRED_DEPLOY_SERVICE_FILES if not (CICD_ROOT / path).is_file()
    ]
    if missing_deploy_services:
        raise ValueError(f"Missing modular deploy service scripts: {missing_deploy_services}")

    missing_infra_deploy_files = [
        path for path in REQUIRED_INFRA_DEPLOY_FILES if not (INFRA_ROOT / path).is_file()
    ]
    if missing_infra_deploy_files:
        raise ValueError(f"Missing infra deployment entrypoints: {missing_infra_deploy_files}")

    production_script = (CICD_ROOT / "scripts" / "deploy" / "production.sh").read_text(
        encoding="utf-8"
    )
    for service_file in REQUIRED_DEPLOY_SERVICE_FILES:
        source_statement = f'source "$script_dir/services/{Path(service_file).name}"'
        if source_statement not in production_script:
            raise ValueError(f"production deploy must source {service_file}")
