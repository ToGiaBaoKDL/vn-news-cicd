from __future__ import annotations

from scripts.workspace.common import APP_ROOT, CICD_ROOT, INFRA_ROOT, WORKSPACE_ROOT

SERVICE_LIFECYCLE_HOOKS = {
    "airflow.sh": (
        "deploy_airflow",
        "provision_airflow",
        "validate_airflow",
        "cleanup_airflow",
    ),
    "app.sh": ("deploy_app", "provision_app", "validate_app", "cleanup_app"),
    "cloudflare.sh": (
        "deploy_data_access",
        "deploy_control_access",
        "provision_cloudflare",
        "validate_cloudflare",
        "cleanup_cloudflare",
    ),
    "ingestion.sh": (
        "deploy_ingestion_workers",
        "provision_ingestion_workers",
        "validate_ingestion_workers",
        "cleanup_ingestion_workers",
    ),
    "polaris.sh": (
        "deploy_polaris",
        "provision_polaris",
        "validate_polaris",
        "cleanup_polaris",
    ),
    "redpanda.sh": (
        "deploy_redpanda",
        "provision_redpanda_schema_registry",
        "provision_redpanda_topics",
        "provision_redpanda_schemas",
        "validate_redpanda",
        "cleanup_redpanda",
    ),
    "seaweedfs.sh": (
        "deploy_seaweedfs",
        "provision_seaweedfs_buckets",
        "validate_seaweedfs",
        "cleanup_seaweedfs",
    ),
    "spark.sh": (
        "deploy_spark_master",
        "deploy_spark_worker",
        "provision_spark",
        "validate_spark_master",
        "validate_spark_worker_registered",
        "cleanup_spark",
    ),
}


def validate_deployment_identity_usage() -> None:
    compose_paths = [APP_ROOT / "compose.yaml", *INFRA_ROOT.rglob("compose*.yaml")]
    for path in compose_paths:
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        if "_IMAGE_TAG" in content:
            relative_path = path.relative_to(WORKSPACE_ROOT)
            raise ValueError(f"{relative_path} must use full per-image refs, not image tags")

    for relative_path in (
        "scripts/deploy/production.sh",
        ".github/workflows/deploy-production.yaml",
    ):
        content = (CICD_ROOT / relative_path).read_text(encoding="utf-8")
        if "inputs.image_tag" in content or "--image-tag" in content:
            raise ValueError(f"{relative_path} must use image manifests, not image tags")

    validate_deploy_workflow()
    validate_deploy_context()
    validate_deploy_service_lifecycle()
    validate_remote_deploy_wrapper()


def validate_deploy_workflow() -> None:
    deploy_workflow = (CICD_ROOT / ".github" / "workflows" / "deploy-production.yaml").read_text(
        encoding="utf-8"
    )
    if "publish-images:" in deploy_workflow:
        raise ValueError("deploy workflow must verify existing images instead of publishing")
    if "python -m scripts.images.build" in deploy_workflow:
        raise ValueError("deploy workflow must not build images")
    if "python -m scripts.images.verify" not in deploy_workflow:
        raise ValueError("deploy workflow must verify deployment images")
    if "digest-pinned image refs" not in deploy_workflow.lower():
        raise ValueError("deploy workflow must document digest-pinned image manifests")

    for fragment in (
        "actions/download-artifact@",
        "actions/upload-artifact@",
        "python -m scripts.images.artifacts",
        "python -m scripts.images.promote",
        "production_manifest_run_id",
        "production-image-manifest",
        "image-manifests/base",
        "image-manifests/updates",
        "steps.artifacts.outputs.app_manifest_run_id",
        "steps.artifacts.outputs.infra_manifest_run_id",
        "steps.artifacts.outputs.services_manifest_run_id",
        "steps.manifest.outputs.image_manifest",
    ):
        if fragment not in deploy_workflow:
            raise ValueError(f"deploy workflow missing promotion fragment: {fragment}")


def validate_deploy_context() -> None:
    deploy_context = (CICD_ROOT / "scripts" / "deploy" / "lib" / "context.sh").read_text(
        encoding="utf-8"
    )
    if '--role "$role"' not in deploy_context:
        raise ValueError("deployment context must render role-scoped image env")
    if (
        "cleanup_image_env" not in deploy_context
        or "--format cleanup-env-names" not in deploy_context
    ):
        raise ValueError("deployment context must refresh image env before deploy")
    if "set_role_env_value" not in deploy_context:
        raise ValueError("deployment context must persist rendered image env")
    if "write_deployment_metadata" not in deploy_context:
        raise ValueError("deployment context must persist deployed commit metadata")


def validate_remote_deploy_wrapper() -> None:
    remote_deploy = (CICD_ROOT / "scripts" / "deploy" / "remote_node.sh").read_text(
        encoding="utf-8"
    )
    for fragment in (
        "preflight_host.sh",
        "production.sh",
        'image_manifest_arg="$(printf',
        '--image-manifest "$image_manifest_arg"',
    ):
        if fragment not in remote_deploy:
            raise ValueError(f"remote deploy wrapper missing fragment: {fragment}")


def validate_deploy_service_lifecycle() -> None:
    service_root = CICD_ROOT / "scripts" / "deploy" / "services"
    for service_file, hooks in SERVICE_LIFECYCLE_HOOKS.items():
        content = (service_root / service_file).read_text(encoding="utf-8")
        for hook in hooks:
            if f"{hook}()" not in content:
                raise ValueError(f"{service_file} missing lifecycle hook: {hook}")
