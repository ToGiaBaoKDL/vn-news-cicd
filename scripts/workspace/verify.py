from __future__ import annotations

import re
from pathlib import Path

import yaml
from news_platform.config import load_settings, load_sources

from scripts.paths import CICD_ROOT, WORKSPACE_ROOT

APP_ROOT = WORKSPACE_ROOT / "vn-news-app"
CONFIG_ROOT = WORKSPACE_ROOT / "vn-news-config"
INFRA_ROOT = WORKSPACE_ROOT / "vn-news-infra"
ORCHESTRATION_ROOT = WORKSPACE_ROOT / "vn-news-orchestration"
PIPELINES_ROOT = WORKSPACE_ROOT / "vn-news-pipelines"
PLATFORM_LIB_ROOT = WORKSPACE_ROOT / "vn-news-platform-lib"
SERVICES_ROOT = WORKSPACE_ROOT / "vn-news-services"
REPOSITORY_ROOTS = (
    APP_ROOT,
    CICD_ROOT,
    CONFIG_ROOT,
    INFRA_ROOT,
    ORCHESTRATION_ROOT,
    PIPELINES_ROOT,
    PLATFORM_LIB_ROOT,
    SERVICES_ROOT,
)
REPOSITORY_NAMES = (
    "vn-news-app",
    "vn-news-cicd",
    "vn-news-config",
    "vn-news-infra",
    "vn-news-orchestration",
    "vn-news-pipelines",
    "vn-news-platform-lib",
    "vn-news-services",
)

ACTION_REF_PATTERN = re.compile(r"uses:\s*([^@\s]+)@([^\s#]+)")
IMMUTABLE_ACTION_REF_PATTERN = re.compile(r"[0-9a-f]{40}")

REQUIRED_SCRIPT_MODULES = (
    "scripts/deploy/refs.py",
    "scripts/images/build.py",
    "scripts/images/catalog.py",
    "scripts/images/manifest.py",
    "scripts/images/tags.py",
    "scripts/images/verify.py",
    "scripts/services/airflow/validate_dag.py",
    "scripts/services/polaris/cli.py",
    "scripts/services/polaris/config.py",
    "scripts/services/polaris/provision.py",
    "scripts/services/polaris/validate.py",
    "scripts/services/polaris/vault.py",
    "scripts/services/redpanda/bootstrap_topics.py",
    "scripts/services/redpanda/register_schemas.py",
    "scripts/services/seaweedfs/bootstrap_buckets.py",
    "scripts/services/spark/validate_cluster.py",
    "scripts/workspace/verify.py",
)
REMOVED_SCRIPT_MODULES = (
    "scripts/bootstrap_polaris.py",
    "scripts/bootstrap_storage.py",
    "scripts/bootstrap_topics.py",
    "scripts/build_images.py",
    "scripts/image_catalog.py",
    "scripts/services/polaris/bootstrap_catalog.py",
    "scripts/services/polaris/catalog.py",
    "scripts/services/polaris/client.py",
    "scripts/services/polaris/common.py",
    "scripts/services/polaris/provision_access.py",
    "scripts/services/polaris/runtime_access.py",
    "scripts/services/polaris/validate_access.py",
    "scripts/polaris_common.py",
    "scripts/prepare_release.py",
    "scripts/provision_polaris_access.py",
    "scripts/images/publish.py",
    "scripts/publish_images.py",
    "scripts/register_event_schemas.py",
    "scripts/release/manifest.py",
    "scripts/release/plan.py",
    "scripts/release/prepare.py",
    "scripts/release/refs.py",
    "scripts/release/tags.py",
    "scripts/release_manifest.py",
    "scripts/release_plan.py",
    "scripts/release_tags.py",
    "scripts/validate_polaris_access.py",
    "scripts/validate_release_refs.py",
    "scripts/validate_workspace.py",
    "scripts/verify_images.py",
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
REMOVED_DEPLOY_SERVICE_FILES = (
    "scripts/deploy/lib/vault.sh",
    "scripts/deploy/services/processing.sh",
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


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def read_env_template(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", maxsplit=1)
        values[key] = value
    return values


def validate_workflow_action_ref(path: Path, action: str, ref: str) -> None:
    if action.startswith("./"):
        return
    if not IMMUTABLE_ACTION_REF_PATTERN.fullmatch(ref):
        msg = f"{path} must pin {action} to an immutable commit SHA, not {ref}"
        raise ValueError(msg)


def validate_workflow_action_pins() -> None:
    for root in REPOSITORY_ROOTS:
        workflow_root = root / ".github" / "workflows"
        if not workflow_root.is_dir():
            continue
        for pattern in ("*.yaml", "*.yml"):
            for path in sorted(workflow_root.glob(pattern)):
                load_yaml(path)
                content = path.read_text(encoding="utf-8")
                for action, ref in ACTION_REF_PATTERN.findall(content):
                    validate_workflow_action_ref(path.relative_to(WORKSPACE_ROOT), action, ref)


def validate_deployment_identity_usage() -> None:
    stale_release_root = CICD_ROOT / "releases"
    if stale_release_root.exists():
        raise ValueError("releases/ must stay removed; deployment identity is commit refs")

    compose_paths = [APP_ROOT / "compose.yaml", *INFRA_ROOT.rglob("compose*.yaml")]
    for path in compose_paths:
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        if "${VN_NEWS_RELEASE_TAG" in content:
            relative_path = path.relative_to(WORKSPACE_ROOT)
            raise ValueError(f"{relative_path} must use image manifest tags")
        if "VN_NEWS_IMAGE_TAG" in content:
            relative_path = path.relative_to(WORKSPACE_ROOT)
            raise ValueError(f"{relative_path} must not use global VN_NEWS_IMAGE_TAG")

    for role in ("data", "control", "processing"):
        env_template = INFRA_ROOT / "env" / f"{role}.env.example"
        content = env_template.read_text(encoding="utf-8")
        required_variables = (
            "VN_NEWS_IMAGE_MANIFEST",
            "VN_NEWS_APP_IMAGE_TAG",
            "VN_NEWS_INFRA_IMAGE_TAG",
            "VN_NEWS_SERVICES_IMAGE_TAG",
            "VN_NEWS_IMAGE_REGISTRY",
            "VN_NEWS_IMAGE_NAMESPACE",
        )
        for variable in required_variables:
            if content.count(f"{variable}=") != 1:
                raise ValueError(f"{env_template} must define {variable} exactly once")
        for variable in ("VN_NEWS_RELEASE_TAG", "VN_NEWS_IMAGE_TAG"):
            if f"{variable}=" in content:
                raise ValueError(f"{env_template} must not define {variable}")

    for relative_path in (
        "scripts/deploy/production.sh",
        "scripts/deploy/lib/context.sh",
        ".github/workflows/deploy-production.yaml",
    ):
        content = (CICD_ROOT / relative_path).read_text(encoding="utf-8")
        for variable in (
            "VN_NEWS_DEPLOY_RELEASE_TAG",
            "VN_NEWS_DEPLOY_IMAGE_TAG",
            "VN_NEWS_IMAGE_TAG",
        ):
            if variable in content:
                raise ValueError(f"{relative_path} must not use {variable}")

    deploy_workflow = (CICD_ROOT / ".github" / "workflows" / "deploy-production.yaml").read_text(
        encoding="utf-8"
    )
    if "publish-images:" in deploy_workflow:
        raise ValueError("deploy workflow must verify existing images instead of publishing")
    if "python -m scripts.images.build" in deploy_workflow:
        raise ValueError("deploy workflow must not build images")
    if "python -m scripts.images.verify" not in deploy_workflow:
        raise ValueError("deploy workflow must verify deployment images")
    if "--image-tag" in deploy_workflow or "inputs.image_tag" in deploy_workflow:
        raise ValueError("deploy workflow must use image_manifest, not a global image tag")

    deploy_context = (CICD_ROOT / "scripts" / "deploy" / "lib" / "context.sh").read_text(
        encoding="utf-8"
    )
    for variable in (
        "VN_NEWS_IMAGE_MANIFEST",
        "VN_NEWS_APP_IMAGE_TAG",
        "VN_NEWS_INFRA_IMAGE_TAG",
        "VN_NEWS_SERVICES_IMAGE_TAG",
        "VN_NEWS_IMAGE_REGISTRY",
        "VN_NEWS_IMAGE_NAMESPACE",
    ):
        if f"set_role_env_value {variable}" not in deploy_context:
            raise ValueError(f"deployment context must persist {variable}")
    if "write_deployment_metadata" not in deploy_context:
        raise ValueError("deployment context must persist deployed commit metadata")


def validate_script_layout() -> None:
    missing_modules = [path for path in REQUIRED_SCRIPT_MODULES if not (CICD_ROOT / path).is_file()]
    if missing_modules:
        raise ValueError(f"Missing modular CICD script modules: {missing_modules}")

    stale_modules = [path for path in REMOVED_SCRIPT_MODULES if (CICD_ROOT / path).exists()]
    if stale_modules:
        raise ValueError(f"Stale CICD script modules must stay removed: {stale_modules}")

    missing_deploy_services = [
        path for path in REQUIRED_DEPLOY_SERVICE_FILES if not (CICD_ROOT / path).is_file()
    ]
    if missing_deploy_services:
        raise ValueError(f"Missing modular deploy service scripts: {missing_deploy_services}")

    stale_deploy_services = [
        path for path in REMOVED_DEPLOY_SERVICE_FILES if (CICD_ROOT / path).exists()
    ]
    if stale_deploy_services:
        raise ValueError(
            f"Redundant deploy service scripts must stay removed: {stale_deploy_services}"
        )

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


def validate_image_catalog() -> None:
    catalog = load_yaml(CICD_ROOT / "images.yaml")
    if catalog.get("version") != 2:
        raise ValueError("images.yaml version must be 2")
    for field in ("registry", "namespace"):
        if not catalog.get(field):
            raise ValueError(f"images.yaml missing required field: {field}")

    owners = catalog.get("owners", {})
    if not isinstance(owners, dict) or not owners:
        raise ValueError("images.yaml must define image owners")
    tag_envs = [owner_config.get("tag_env") for owner_config in owners.values()]
    duplicate_tag_envs = sorted(tag_env for tag_env in set(tag_envs) if tag_envs.count(tag_env) > 1)
    if duplicate_tag_envs:
        raise ValueError(f"Duplicate image owner tag envs in images.yaml: {duplicate_tag_envs}")
    for owner, owner_config in sorted(owners.items()):
        if owner not in REPOSITORY_NAMES:
            raise ValueError(f"Unknown image owner repository in images.yaml: {owner}")
        if not owner_config.get("tag_env"):
            raise ValueError(f"Image owner {owner} is missing tag_env")
        source_repositories = owner_config.get("source_repositories")
        if not isinstance(source_repositories, list) or not source_repositories:
            raise ValueError(f"Image owner {owner} is missing source_repositories")
        unknown_sources = sorted(set(source_repositories) - set(REPOSITORY_NAMES))
        if unknown_sources:
            raise ValueError(f"Image owner {owner} has unknown sources: {unknown_sources}")

    repositories: list[str] = []
    images_by_owner: dict[str, set[str]] = {owner: set() for owner in owners}
    for image_key, image in catalog.get("images", {}).items():
        owner = image.get("owner")
        if owner not in owners:
            raise ValueError(f"Image {image_key} has unknown owner: {owner}")
        if "build" in image:
            raise ValueError(f"Deployment image catalog must not define build for {image_key}")
        images_by_owner[owner].add(image_key)
        repository = image.get("image_repository")
        if not repository:
            raise ValueError(f"Image {image_key} is missing image_repository")
        repositories.append(repository)

    duplicates = sorted(
        repository for repository in set(repositories) if repositories.count(repository) > 1
    )
    if duplicates:
        raise ValueError(f"Duplicate Docker image repositories in images.yaml: {duplicates}")

    validate_source_image_catalogs(catalog, images_by_owner)


SOURCE_IMAGE_CATALOGS = {
    "vn-news-app": APP_ROOT,
    "vn-news-infra": INFRA_ROOT,
    "vn-news-services": SERVICES_ROOT,
}


def validate_source_image_catalogs(
    deploy_catalog: dict,
    deploy_images_by_owner: dict[str, set[str]],
) -> None:
    for owner, root in SOURCE_IMAGE_CATALOGS.items():
        catalog_path = root / "images.yaml"
        if not catalog_path.is_file():
            raise ValueError(f"{owner} must define images.yaml")
        source_catalog = load_yaml(catalog_path)
        if source_catalog.get("version") != 1:
            raise ValueError(f"{catalog_path} version must be 1")
        if source_catalog.get("owner") != owner:
            raise ValueError(f"{catalog_path} owner must be {owner}")
        source_images = set(source_catalog.get("images", {}))
        if source_images != deploy_images_by_owner.get(owner, set()):
            raise ValueError(f"{catalog_path} images must match deployment catalog")
        for image_key, image in source_catalog.get("images", {}).items():
            deploy_image = deploy_catalog["images"][image_key]
            if image.get("image_repository") != deploy_image.get("image_repository"):
                raise ValueError(f"{catalog_path} repository drift for {image_key}")
            validate_image_build(image_key, image.get("build", {}))
        validate_source_image_workflow(owner, root)


def validate_source_image_workflow(owner: str, root: Path) -> None:
    workflow_path = root / ".github" / "workflows" / "publish-images.yaml"
    if not workflow_path.is_file():
        raise ValueError(f"{owner} must define publish-images workflow")
    workflow = workflow_path.read_text(encoding="utf-8")
    required_fragments = (
        "python -m scripts.images.build",
        f"--catalog ../{owner}/images.yaml",
        "--workspace-root ..",
        "--push",
    )
    for fragment in required_fragments:
        if fragment not in workflow:
            raise ValueError(f"{workflow_path} missing image publish fragment: {fragment}")
    if owner in {"vn-news-app", "vn-news-services"} and "platform_lib_ref" not in workflow:
        raise ValueError(f"{workflow_path} must include platform_lib_ref input")


def validate_image_build(image_key: str, build: dict) -> None:
    allowed_fields = {"additional_contexts", "context", "dockerfile"}
    extra_fields = sorted(set(build) - allowed_fields)
    if extra_fields:
        raise ValueError(f"Image {image_key} build has unused fields: {extra_fields}")

    context = build.get("context")
    context_path = WORKSPACE_ROOT / str(context)
    if context is None or not context_path.is_dir():
        raise ValueError(f"Image {image_key} references missing build context: {context}")
    if not (context_path / ".dockerignore").is_file():
        raise ValueError(f"Image {image_key} build context is missing .dockerignore: {context}")

    dockerfile = build.get("dockerfile")
    if not dockerfile or not (context_path / dockerfile).is_file():
        raise ValueError(f"Image {image_key} references missing Dockerfile: {dockerfile}")

    for name, path in sorted(build.get("additional_contexts", {}).items()):
        if not (WORKSPACE_ROOT / path).is_dir():
            raise ValueError(f"Image {image_key} additional context {name} is missing: {path}")


def validate_role_env_templates() -> None:
    env_by_role = {
        role: read_env_template(INFRA_ROOT / "env" / f"{role}.env.example")
        for role in ("data", "control", "processing")
    }

    data_env = env_by_role["data"]
    required_data = {
        "VN_NEWS_POLARIS_CATALOG_URL",
        "VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID",
        "VN_NEWS_POLARIS_REALM",
    }
    missing = sorted(required_data - set(data_env))
    if missing:
        raise ValueError(f"data env is missing required Polaris runtime settings: {missing}")

    control_env = env_by_role["control"]
    required_control = {
        "VN_NEWS_CONTROL_PRIVATE_IP",
        "VN_NEWS_SPARK_IMAGE",
        "VN_NEWS_SPARK_MASTER_PORT",
        "VN_NEWS_SPARK_MASTER_UI_PORT",
        "VN_NEWS_SPARK_DRIVER_PORT",
        "VN_NEWS_SPARK_BLOCK_MANAGER_PORT",
        "VN_NEWS_SPARK_CHECKPOINT_ROOT",
        "VN_NEWS_POLARIS_CATALOG_URL",
        "VN_NEWS_POLARIS_REALM",
        "VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID",
        "VN_NEWS_SPARK_RPC_AUTH_SECRET_OCID",
        "VN_NEWS_AIRFLOW_EXPECTED_DAG_ID",
    }
    missing = sorted(required_control - set(control_env))
    if missing:
        raise ValueError(f"control env is missing required Spark settings: {missing}")

    processing_env = env_by_role["processing"]
    required_processing = {
        "VN_NEWS_CONFIG_HOST_DIR",
        "VN_NEWS_IMAGE_NAMESPACE",
        "VN_NEWS_IMAGE_REGISTRY",
        "VN_NEWS_INGESTION_S3_CREDENTIALS_SECRET_OCID",
        "VN_NEWS_PROCESSING_PRIVATE_IP",
        "VN_NEWS_REDPANDA_BOOTSTRAP_SERVERS",
        "VN_NEWS_SCHEMA_REGISTRY_URL",
        "VN_NEWS_SPARK_IMAGE",
        "VN_NEWS_SPARK_MASTER_URL",
        "VN_NEWS_SPARK_MASTER_UI_PORT",
        "VN_NEWS_SPARK_WORKER_PORT",
        "VN_NEWS_SPARK_WORKER_UI_PORT",
        "VN_NEWS_SPARK_WORKER_CORES",
        "VN_NEWS_SPARK_WORKER_MEMORY",
        "VN_NEWS_SPARK_WORKER_DIR",
        "VN_NEWS_SPARK_LOCAL_DIR",
        "VN_NEWS_SPARK_RPC_AUTH_SECRET_OCID",
    }
    missing = sorted(required_processing - set(processing_env))
    if missing:
        raise ValueError(f"processing env is missing required Spark worker settings: {missing}")

    forbidden_processing = {
        "VN_NEWS_CURATED_WRITER_S3_CREDENTIALS_SECRET_OCID",
        "VN_NEWS_POLARIS_CATALOG_URL",
        "VN_NEWS_POLARIS_CATALOG_NAME",
        "VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID",
        "VN_NEWS_POLARIS_REALM",
        "VN_NEWS_SPARK_CHECKPOINT_ROOT",
    }
    present = sorted(forbidden_processing & set(processing_env))
    if present:
        raise ValueError(f"processing env has stale Spark credential settings: {present}")

    spark_images = {control_env["VN_NEWS_SPARK_IMAGE"], processing_env["VN_NEWS_SPARK_IMAGE"]}
    if len(spark_images) != 1 or not next(iter(spark_images)).startswith("apache/spark:"):
        raise ValueError("Spark master and worker must use one pinned official apache/spark image")


def validate_settings_load() -> None:
    settings = load_settings()
    sources = load_sources(settings=settings)
    if not settings.get("project", {}).get("name"):
        raise ValueError("settings.yaml must define project.name")
    if not sources:
        raise ValueError("source configuration must contain at least one source")


def main() -> None:
    validate_workflow_action_pins()
    validate_deployment_identity_usage()
    validate_script_layout()
    validate_image_catalog()
    validate_role_env_templates()
    validate_settings_load()
    print("workspace verification ok")


if __name__ == "__main__":
    main()
