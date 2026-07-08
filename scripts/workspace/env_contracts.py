from __future__ import annotations

from scripts.workspace.common import (
    CICD_ROOT,
    DEPLOY_ROLES,
    INFRA_ROOT,
    load_yaml,
    missing_keys,
    read_env_template,
)


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
        missing_image_env = missing_keys(required_image_env_by_role[role], env)
        if missing_image_env:
            raise ValueError(f"{role} env is missing image refs: {missing_image_env}")

    validate_data_env(env_by_role["data"])
    validate_control_env(env_by_role["control"])
    validate_processing_env(env_by_role["processing"])


def validate_data_env(data_env: dict[str, str]) -> None:
    required_data = {
        "VN_NEWS_POLARIS_CATALOG_URL",
        "VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID",
        "VN_NEWS_POLARIS_REALM",
    }
    missing = missing_keys(required_data, data_env)
    if missing:
        raise ValueError(f"data env is missing required Polaris runtime settings: {missing}")


def validate_control_env(control_env: dict[str, str]) -> None:
    required_control = {
        "VN_NEWS_CONTROL_PRIVATE_IP",
        "VN_NEWS_SPARK_MASTER_PORT",
        "VN_NEWS_SPARK_MASTER_UI_PORT",
        "VN_NEWS_SPARK_DRIVER_PORT",
        "VN_NEWS_SPARK_BLOCK_MANAGER_PORT",
        "VN_NEWS_SPARK_CHECKPOINT_ROOT",
        "VN_NEWS_POLARIS_CATALOG_URL",
        "VN_NEWS_POLARIS_REALM",
        "VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID",
        "VN_NEWS_SPARK_RPC_AUTH_SECRET_OCID",
    }
    missing = missing_keys(required_control, control_env)
    if missing:
        raise ValueError(f"control env is missing required Spark settings: {missing}")


def validate_processing_env(processing_env: dict[str, str]) -> None:
    required_processing = {
        "VN_NEWS_CONFIG_HOST_DIR",
        "VN_NEWS_INGESTION_S3_CREDENTIALS_SECRET_OCID",
        "VN_NEWS_PROCESSING_PRIVATE_IP",
        "VN_NEWS_REDPANDA_BOOTSTRAP_SERVERS",
        "VN_NEWS_SCHEMA_REGISTRY_URL",
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
    missing = missing_keys(required_processing, processing_env)
    if missing:
        raise ValueError(f"processing env is missing required Spark worker settings: {missing}")
