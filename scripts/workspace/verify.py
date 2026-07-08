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
DEPLOY_ROLES = ("data", "control", "processing")

ACTION_REF_PATTERN = re.compile(r"uses:\s*([^@\s]+)@([^\s#]+)")
IMMUTABLE_ACTION_REF_PATTERN = re.compile(r"[0-9a-f]{40}")

REQUIRED_SCRIPT_MODULES = (
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
        "production-image-manifest",
        "image-manifests/updates",
        "steps.artifacts.outputs.app_manifest_run_id",
        "steps.artifacts.outputs.infra_manifest_run_id",
        "steps.artifacts.outputs.services_manifest_run_id",
        "steps.manifest.outputs.image_manifest",
    ):
        if fragment not in deploy_workflow:
            raise ValueError(f"deploy workflow missing promotion fragment: {fragment}")

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


def validate_script_layout() -> None:
    missing_modules = [path for path in REQUIRED_SCRIPT_MODULES if not (CICD_ROOT / path).is_file()]
    if missing_modules:
        raise ValueError(f"Missing modular CICD script modules: {missing_modules}")

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
    for owner, owner_config in sorted(owners.items()):
        if owner not in REPOSITORY_NAMES:
            raise ValueError(f"Unknown image owner repository in images.yaml: {owner}")
        source_repositories = owner_config.get("source_repositories")
        if not isinstance(source_repositories, list) or not source_repositories:
            raise ValueError(f"Image owner {owner} is missing source_repositories")
        unknown_sources = sorted(set(source_repositories) - set(REPOSITORY_NAMES))
        if unknown_sources:
            raise ValueError(f"Image owner {owner} has unknown sources: {unknown_sources}")

    repositories: list[str] = []
    image_envs: list[str] = []
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
        image_env = image.get("image_env")
        if not isinstance(image_env, str) or not image_env.startswith("VN_NEWS_"):
            raise ValueError(f"Image {image_key} is missing VN_NEWS_* image_env")
        image_envs.append(image_env)
        roles = image.get("roles")
        if not isinstance(roles, list):
            raise ValueError(f"Image {image_key} roles must be a list")
        unknown_roles = sorted(set(roles) - set(DEPLOY_ROLES))
        if unknown_roles:
            raise ValueError(f"Image {image_key} has unknown deploy roles: {unknown_roles}")

    duplicates = sorted(
        repository for repository in set(repositories) if repositories.count(repository) > 1
    )
    if duplicates:
        raise ValueError(f"Duplicate Docker image repositories in images.yaml: {duplicates}")
    duplicate_image_envs = sorted(
        image_env for image_env in set(image_envs) if image_envs.count(image_env) > 1
    )
    if duplicate_image_envs:
        raise ValueError(f"Duplicate image env variables in images.yaml: {duplicate_image_envs}")

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
        validate_change_paths(catalog_path, "catalog", source_catalog.get("change_paths"))
        source_images = set(source_catalog.get("images", {}))
        if source_images != deploy_images_by_owner.get(owner, set()):
            raise ValueError(f"{catalog_path} images must match deployment catalog")
        for image_key, image in source_catalog.get("images", {}).items():
            deploy_image = deploy_catalog["images"][image_key]
            if image.get("image_repository") != deploy_image.get("image_repository"):
                raise ValueError(f"{catalog_path} repository drift for {image_key}")
            validate_change_paths(catalog_path, image_key, image.get("change_paths"))
            validate_image_build(image_key, image.get("build", {}))
        validate_source_image_workflow(owner, root)


def validate_change_paths(catalog_path: Path, scope: str, change_paths: object) -> None:
    if not isinstance(change_paths, list) or not change_paths:
        raise ValueError(f"{catalog_path} {scope} must define change_paths")
    invalid = [path for path in change_paths if not isinstance(path, str) or not path.strip()]
    if invalid:
        raise ValueError(f"{catalog_path} {scope} has invalid change_paths: {invalid}")
    if ".github/workflows/publish-images.yaml" in change_paths:
        raise ValueError(f"{catalog_path} {scope} must not rebuild images for workflow-only edits")


def validate_source_image_workflow(owner: str, root: Path) -> None:
    workflow_path = root / ".github" / "workflows" / "publish-images.yaml"
    if not workflow_path.is_file():
        raise ValueError(f"{owner} must define publish-images workflow")
    workflow = workflow_path.read_text(encoding="utf-8")
    required_fragments = (
        "fetch-depth: 0",
        "python -m scripts.images.changed",
        "python -m scripts.images.build",
        "python -m scripts.images.digests",
        "actions/upload-artifact@",
        "image-manifest/image-manifest.json",
        f"--catalog ../{owner}/images.yaml",
        "--workspace-root ..",
        "--push",
        "steps.images.outputs.has_changes",
        "steps.images.outputs.image_args",
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
        role: read_env_template(INFRA_ROOT / "env" / f"{role}.env.example") for role in DEPLOY_ROLES
    }
    deploy_catalog = load_yaml(CICD_ROOT / "images.yaml")
    required_image_env_by_role = {
        role: {
            image["image_env"]
            for image in deploy_catalog["images"].values()
            if role in image.get("roles", [])
        }
        for role in DEPLOY_ROLES
    }

    for role, env in env_by_role.items():
        if "VN_NEWS_IMAGE_MANIFEST" not in env:
            raise ValueError(f"{role} env is missing VN_NEWS_IMAGE_MANIFEST")
        stale = sorted(
            key
            for key in env
            if key.endswith("_IMAGE_TAG")
            or key in {"VN_NEWS_IMAGE_REGISTRY", "VN_NEWS_IMAGE_NAMESPACE"}
        )
        if stale:
            raise ValueError(f"{role} env has stale image variables: {stale}")
        missing_image_env = sorted(required_image_env_by_role[role] - set(env))
        if missing_image_env:
            raise ValueError(f"{role} env is missing image refs: {missing_image_env}")

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
