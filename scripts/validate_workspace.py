from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml
from news_platform.config import load_settings, load_sources
from news_platform.contracts.events import EVENT_CONTRACTS, EVENT_TOPIC_KEYS

from scripts.release_manifest import RELEASES_ROOT, load_release_manifest

CICD_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = CICD_ROOT.parent

APP_ROOT = WORKSPACE_ROOT / "vn-news-app"
CONFIG_ROOT = WORKSPACE_ROOT / "vn-news-config"
CONFIG_DIR = CONFIG_ROOT / "configs"
INFRA_ROOT = WORKSPACE_ROOT / "vn-news-infra"
ORCHESTRATION_ROOT = WORKSPACE_ROOT / "vn-news-orchestration"
PLATFORM_LIB_ROOT = WORKSPACE_ROOT / "vn-news-platform-lib"
SERVICES_ROOT = WORKSPACE_ROOT / "vn-news-services"
REPOSITORY_ROOTS = [
    APP_ROOT,
    CICD_ROOT,
    CONFIG_ROOT,
    INFRA_ROOT,
    ORCHESTRATION_ROOT,
    PLATFORM_LIB_ROOT,
    SERVICES_ROOT,
]
ACTION_REF_PATTERN = re.compile(r"uses:\s*([^@\s]+)@([^\s#]+)")
IMMUTABLE_ACTION_REF_PATTERN = re.compile(r"[0-9a-f]{40}")


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_toml(path: Path) -> dict:
    with path.open("rb") as file:
        return tomllib.load(file)


def load_compose(filename: str = "compose.yaml") -> dict:
    compose = load_yaml(INFRA_ROOT / filename)
    services: dict = {}
    volumes: dict = {}
    for include in compose.get("include", []):
        include_path = include["path"] if isinstance(include, dict) else include
        included = load_yaml(INFRA_ROOT / include_path)
        services.update(included.get("services", {}))
        volumes.update(included.get("volumes", {}))
    compose["services"] = services
    compose["volumes"] = volumes
    return compose


def load_image_catalog() -> dict:
    return load_yaml(CICD_ROOT / "images.yaml")


def validate_release_manifests() -> None:
    manifests = sorted(RELEASES_ROOT.glob("*.toml"))
    if not manifests:
        raise ValueError("releases/ must contain at least one release manifest")
    for path in manifests:
        load_release_manifest(path)


def validate_workflow_action_ref(path: Path, action: str, ref: str) -> None:
    if action.startswith("./"):
        return
    if not IMMUTABLE_ACTION_REF_PATTERN.fullmatch(ref):
        msg = f"{path} must pin {action} to an immutable commit SHA, not {ref}"
        raise ValueError(msg)


def validate_workflow_action_pins() -> None:
    for root in REPOSITORY_ROOTS:
        workflow_root = root / ".github" / "workflows"
        for pattern in ("*.yaml", "*.yml"):
            for path in sorted(workflow_root.glob(pattern)):
                content = path.read_text(encoding="utf-8")
                for action, ref in ACTION_REF_PATTERN.findall(content):
                    validate_workflow_action_ref(path.relative_to(WORKSPACE_ROOT), action, ref)


def validate_settings_consistency(config: dict) -> None:
    project_name = config["project"]["name"]
    compose_name = load_compose()["name"]
    if compose_name != project_name:
        msg = f"Compose name must match project.name: {compose_name} != {project_name}"
        raise ValueError(msg)


def validate_platform_services(config: dict) -> None:
    compose_services = load_compose()["services"]
    required_services = set()
    if config["event_bus"]["provider"] == "redpanda":
        required_services.add("redpanda")
    if config["storage"]["provider"] == "seaweedfs_s3":
        required_services.add("seaweedfs-s3")
    missing_services = sorted(required_services - set(compose_services))
    if missing_services:
        msg = f"Compose is missing configured platform services: {missing_services}"
        raise ValueError(msg)

    forbidden_services = sorted({"api", "web"} & set(compose_services))
    if forbidden_services:
        msg = f"Infra compose must not own app services: {forbidden_services}"
        raise ValueError(msg)


def validate_cloudflare_access() -> None:
    cloudflare_root = INFRA_ROOT / "access" / "cloudflare"
    required_files = {
        "compose.control.yaml",
        "compose.data.yaml",
    }
    missing_files = sorted(
        path for path in required_files if not (cloudflare_root / path).is_file()
    )
    if missing_files:
        raise ValueError(f"vn-news-infra missing Cloudflare access files: {missing_files}")
    for filename in required_files:
        compose = load_yaml(cloudflare_root / filename)
        for service_name, service in compose.get("services", {}).items():
            image = service.get("image", "")
            if ":latest" in image:
                raise ValueError(f"{service_name} must not use a latest cloudflared image")
            command = service.get("command", [])
            if "--token-file" not in command:
                raise ValueError(f"{service_name} must read tunnel tokens from a secret file")
            if "--metrics" not in command:
                raise ValueError(f"{service_name} must expose cloudflared metrics explicitly")
            metrics_index = command.index("--metrics") + 1
            if metrics_index >= len(command):
                raise ValueError(f"{service_name} must set a cloudflared metrics address")
            metrics_address = command[metrics_index]
            if not metrics_address.startswith(("127.0.0.1:", "localhost:")):
                raise ValueError(
                    f"{service_name} cloudflared metrics must bind to loopback: {metrics_address}"
                )
            token_index = command.index("--token-file") + 1
            if token_index >= len(command):
                raise ValueError(f"{service_name} must set a token file path")
            token_path = command[token_index]
            volumes = service.get("volumes", [])
            token_mount = next(
                (
                    volume
                    for volume in volumes
                    if isinstance(volume, dict) and volume.get("target") == token_path
                ),
                None,
            )
            if token_mount is None:
                raise ValueError(f"{service_name} must bind mount its token file")
            if token_mount.get("read_only") is not True:
                raise ValueError(f"{service_name} token file mount must be read-only")
            if token_mount.get("bind", {}).get("create_host_path") is not False:
                raise ValueError(f"{service_name} token file mount must not create host paths")


def validate_source_filenames() -> None:
    for path in sorted((CONFIG_DIR / "sources").glob("*.yaml")):
        source = load_yaml(path)
        expected = f"{source['source_id']}.yaml"
        if path.name != expected:
            msg = (
                f"Source config filename '{path.name}' must match source_id '{source['source_id']}'"
            )
            raise ValueError(msg)


def validate_platform_lib_package() -> None:
    pyproject = load_toml(PLATFORM_LIB_ROOT / "pyproject.toml")
    if pyproject["project"]["name"] != "news-platform-lib":
        raise ValueError("vn-news-platform-lib project.name must be news-platform-lib")
    wheel_packages = (
        pyproject.get("tool", {})
        .get("hatch", {})
        .get("build", {})
        .get("targets", {})
        .get("wheel", {})
        .get("packages", [])
    )
    expected = ["src/news_platform"]
    if sorted(wheel_packages) != expected:
        msg = f"news-platform-lib wheel packages must be {expected}"
        raise ValueError(msg)


def validate_python_dependency_sources(pyproject_path: Path) -> None:
    pyproject = load_toml(pyproject_path)
    dependencies = {
        normalize_dependency_name(dependency)
        for dependency in pyproject.get("project", {}).get("dependencies", [])
    }
    sources = pyproject.get("tool", {}).get("uv", {}).get("sources", {})
    deprecated_dependencies = {"news-common", "news-contracts", "news-shared"} & dependencies
    if deprecated_dependencies:
        msg = (
            f"{pyproject_path} must depend on news-platform-lib, not "
            f"{sorted(deprecated_dependencies)}"
        )
        raise ValueError(msg)
    if "news-platform-lib" in dependencies and "news-platform-lib" not in sources:
        msg = f"{pyproject_path} depends on news-platform-lib but has no local uv source"
        raise ValueError(msg)


def normalize_dependency_name(dependency: str) -> str:
    return re.split(r"[\[<>=!~; ]", dependency, maxsplit=1)[0]


def validate_app() -> None:
    root_pyproject = load_toml(APP_ROOT / "pyproject.toml")
    if root_pyproject["tool"]["uv"]["workspace"]["members"] != ["api"]:
        raise ValueError("vn-news-app uv workspace members must be ['api']")

    api_pyproject_path = APP_ROOT / "api" / "pyproject.toml"
    api_pyproject = load_toml(api_pyproject_path)
    if api_pyproject["project"]["name"] != "news-api":
        raise ValueError("App API project.name must be news-api")
    if not (APP_ROOT / "api" / "Dockerfile").is_file():
        raise ValueError("App API must own api/Dockerfile")
    if not (APP_ROOT / "web" / "Dockerfile").is_file():
        raise ValueError("App web must own web/Dockerfile")
    if not (APP_ROOT / "web" / "package.json").is_file():
        raise ValueError("App web must own web/package.json")
    validate_python_dependency_sources(api_pyproject_path)


def validate_services() -> None:
    root_pyproject = load_toml(SERVICES_ROOT / "pyproject.toml")
    expected_members = [
        "services/common",
        "services/feed_ingestor",
        "services/article_fetcher",
        "services/article_extractor",
        "services/pipeline_metrics",
        "services/dlq_operator",
    ]
    if root_pyproject["tool"]["uv"]["workspace"]["members"] != expected_members:
        msg = f"vn-news-services uv workspace members must be {expected_members}"
        raise ValueError(msg)

    package_names = {
        "services/common": "news-service-common",
        "services/feed_ingestor": "news-feed-ingestor",
        "services/article_fetcher": "news-article-fetcher",
        "services/article_extractor": "news-article-extractor",
        "services/pipeline_metrics": "news-pipeline-metrics",
        "services/dlq_operator": "news-dlq-operator",
    }
    for package_dir, expected_name in package_names.items():
        pyproject_path = SERVICES_ROOT / package_dir / "pyproject.toml"
        pyproject = load_toml(pyproject_path)
        if pyproject["project"]["name"] != expected_name:
            msg = f"{package_dir} project.name must be {expected_name}"
            raise ValueError(msg)
        validate_python_dependency_sources(pyproject_path)


def validate_orchestration() -> None:
    required_files = {
        ".airflowignore",
        "configs/rss_ingestion.yaml",
        "dags/etl_docker_rss_ingestion.py",
        "utils/config.py",
        "utils/env.py",
        "utils/sources.py",
    }
    missing_files = sorted(
        path for path in required_files if not (ORCHESTRATION_ROOT / path).is_file()
    )
    if missing_files:
        raise ValueError(f"vn-news-orchestration missing files: {missing_files}")
    forbidden_files = [
        "Dockerfile",
        ".dockerignore",
        "pyproject.toml",
        "uv.lock",
        "news_orchestration",
        "news_orchestration/__init__.py",
    ]
    present_forbidden = sorted(
        path for path in forbidden_files if (ORCHESTRATION_ROOT / path).exists()
    )
    if present_forbidden:
        raise ValueError(f"vn-news-orchestration has forbidden files: {present_forbidden}")


def validate_image_catalog() -> None:
    catalog = load_image_catalog()

    if catalog.get("version") != 1:
        raise ValueError("images.yaml version must be 1")
    for field in ("registry", "namespace"):
        if not catalog.get(field):
            msg = f"images.yaml missing required field: {field}"
            raise ValueError(msg)
    image_repositories = []
    catalog_dockerfiles = []
    for image_key, image in catalog.get("images", {}).items():
        image_repository = image.get("image_repository")
        if not image_repository:
            msg = f"Image {image_key} is missing image_repository"
            raise ValueError(msg)
        image_repositories.append(image_repository)
        catalog_dockerfiles.append(validate_image_build(image_key, image.get("build", {})))

    duplicate_image_repositories = sorted(
        image_repository
        for image_repository in set(image_repositories)
        if image_repositories.count(image_repository) > 1
    )
    if duplicate_image_repositories:
        msg = f"Duplicate Docker image repositories in images.yaml: {duplicate_image_repositories}"
        raise ValueError(msg)
    validate_catalog_dockerfiles(catalog_dockerfiles)


def validate_image_build(image_key: str, build: dict) -> Path:
    context = build.get("context")
    context_path = WORKSPACE_ROOT / str(context)
    if context is None or not context_path.is_dir():
        msg = f"Image {image_key} references missing build context: {context}"
        raise ValueError(msg)
    if not (context_path / ".dockerignore").is_file():
        msg = f"Image {image_key} build context is missing .dockerignore: {context}"
        raise ValueError(msg)
    dockerfile = build.get("dockerfile")
    if not dockerfile or not (context_path / dockerfile).is_file():
        msg = f"Image {image_key} references missing Dockerfile: {dockerfile}"
        raise ValueError(msg)
    additional_contexts = build.get("additional_contexts", {}).values()
    missing_contexts = sorted(
        path for path in additional_contexts if not (WORKSPACE_ROOT / path).is_dir()
    )
    if missing_contexts:
        msg = f"Image {image_key} references missing additional contexts: {missing_contexts}"
        raise ValueError(msg)
    missing_context_ignores = sorted(
        path
        for path in additional_contexts
        if not (WORKSPACE_ROOT / path / ".dockerignore").is_file()
    )
    if missing_context_ignores:
        msg = (
            f"Image {image_key} additional contexts missing .dockerignore: "
            f"{missing_context_ignores}"
        )
        raise ValueError(msg)
    repo = build.get("repo")
    if repo and not (WORKSPACE_ROOT / repo).is_dir():
        msg = f"Image {image_key} references missing repo: {repo}"
        raise ValueError(msg)

    build_type = build.get("type")
    if build_type == "python_package":
        package_dir = build.get("package_dir")
        package_name = build.get("package_name")
        pyproject_path = WORKSPACE_ROOT / repo / package_dir / "pyproject.toml"
        if not pyproject_path.exists():
            msg = f"Image {image_key} references missing package pyproject: {package_dir}"
            raise ValueError(msg)
        actual_package_name = load_toml(pyproject_path)["project"]["name"]
        if actual_package_name != package_name:
            msg = f"Image {image_key} package_name must be {actual_package_name}"
            raise ValueError(msg)
    elif build_type == "python_project":
        project_dir = build.get("project_dir", ".")
        if not (WORKSPACE_ROOT / repo / project_dir / "pyproject.toml").exists():
            msg = f"Image {image_key} references missing Python project: {repo}/{project_dir}"
            raise ValueError(msg)
    elif build_type == "node_app":
        app_dir = build.get("app_dir")
        if not (WORKSPACE_ROOT / repo / app_dir / "package.json").exists():
            msg = f"Image {image_key} references missing node app: {app_dir}"
            raise ValueError(msg)
    else:
        msg = f"Unsupported image build type for {image_key}: {build_type}"
        raise ValueError(msg)
    return (context_path / dockerfile).resolve()


def validate_catalog_dockerfiles(catalog_dockerfiles: list[Path]) -> None:
    roots = [APP_ROOT, INFRA_ROOT, SERVICES_ROOT]
    actual_dockerfiles = {path.resolve() for root in roots for path in root.rglob("Dockerfile")}
    missing_entries = sorted(
        str(path.relative_to(WORKSPACE_ROOT))
        for path in actual_dockerfiles - set(catalog_dockerfiles)
    )
    if missing_entries:
        msg = f"Dockerfiles missing from images.yaml: {missing_entries}"
        raise ValueError(msg)


def validate_uv_projects() -> None:
    project_roots = [
        APP_ROOT,
        CICD_ROOT,
        INFRA_ROOT / "airflow" / "runtime",
        PLATFORM_LIB_ROOT,
        SERVICES_ROOT,
    ]
    for root in project_roots:
        for filename in ("pyproject.toml", "uv.lock"):
            path = root / filename
            if not path.is_file():
                msg = f"uv project is missing {path.relative_to(WORKSPACE_ROOT)}"
                raise ValueError(msg)
        validate_python_dependency_sources(root / "pyproject.toml")

    python_dockerfiles = [
        APP_ROOT / "api" / "Dockerfile",
        INFRA_ROOT / "airflow" / "runtime" / "Dockerfile",
        SERVICES_ROOT / "services" / "feed_ingestor" / "Dockerfile",
        SERVICES_ROOT / "services" / "article_fetcher" / "Dockerfile",
        SERVICES_ROOT / "services" / "article_extractor" / "Dockerfile",
        SERVICES_ROOT / "services" / "pipeline_metrics" / "Dockerfile",
        SERVICES_ROOT / "services" / "dlq_operator" / "Dockerfile",
    ]
    for path in python_dockerfiles:
        dockerfile = path.read_text(encoding="utf-8")
        if "ghcr.io/astral-sh/uv:" not in dockerfile:
            msg = f"Python Dockerfile must install with uv: {path.relative_to(WORKSPACE_ROOT)}"
            raise ValueError(msg)
        if "--frozen" not in dockerfile:
            msg = f"Python Dockerfile must use frozen uv lock: {path.relative_to(WORKSPACE_ROOT)}"
            raise ValueError(msg)
        if "uv sync " in dockerfile and "ENV UV_PROJECT_ENVIRONMENT=/app/.venv" not in dockerfile:
            msg = (
                f"uv sync Dockerfile must install into /app/.venv: "
                f"{path.relative_to(WORKSPACE_ROOT)}"
            )
            raise ValueError(msg)


def validate_compose_healthchecks() -> None:
    compose_files = {
        "infra data": load_compose("compose.data.yaml"),
        "infra control": load_compose("compose.control.yaml"),
        "infra processing": load_compose("compose.processing.yaml"),
        "app": load_yaml(APP_ROOT / "compose.yaml"),
    }
    for owner, compose in compose_files.items():
        missing_healthchecks = sorted(
            service_name
            for service_name, service in compose["services"].items()
            if "healthcheck" not in service and not service.get("profiles")
        )
        if missing_healthchecks:
            msg = f"{owner} Compose services must define healthchecks: {missing_healthchecks}"
            raise ValueError(msg)


def validate_release_identity_usage() -> None:
    compose_paths = [APP_ROOT / "compose.yaml", *INFRA_ROOT.rglob("compose*.yaml")]
    for path in compose_paths:
        content = path.read_text(encoding="utf-8")
        if "${VN_NEWS_RELEASE_TAG" in content:
            relative_path = path.relative_to(WORKSPACE_ROOT)
            raise ValueError(f"{relative_path} must use VN_NEWS_IMAGE_TAG for images")

    for role in ("data", "control", "processing"):
        env_template = INFRA_ROOT / "env" / f"{role}.env.example"
        content = env_template.read_text(encoding="utf-8")
        for variable in ("VN_NEWS_RELEASE_TAG", "VN_NEWS_IMAGE_TAG"):
            if content.count(f"{variable}=") != 1:
                raise ValueError(f"{env_template} must define {variable} exactly once")

    deploy_script = (CICD_ROOT / "scripts" / "deploy_production.sh").read_text(encoding="utf-8")
    for variable in ("VN_NEWS_DEPLOY_RELEASE_TAG", "VN_NEWS_DEPLOY_IMAGE_TAG"):
        if variable not in deploy_script:
            raise ValueError(f"deploy_production.sh must pass {variable}")

    deploy_context = (CICD_ROOT / "scripts" / "deploy" / "lib" / "context.sh").read_text(
        encoding="utf-8"
    )
    for variable in ("VN_NEWS_IMAGE_REGISTRY", "VN_NEWS_IMAGE_NAMESPACE"):
        if f"set_role_env_value {variable}" not in deploy_context:
            raise ValueError(f"deployment context must persist {variable}")


def validate_recovery_controls() -> None:
    required_scripts = {
        "scripts/configure_host_operations.sh",
        "scripts/export_recovery.sh",
        "scripts/publish_host_metrics.sh",
        "scripts/verify_recovery_restore.sh",
    }
    missing_scripts = sorted(path for path in required_scripts if not (INFRA_ROOT / path).is_file())
    if missing_scripts:
        raise ValueError(f"vn-news-infra missing recovery scripts: {missing_scripts}")

    for role in ("data", "control"):
        env_template = INFRA_ROOT / "env" / f"{role}.env.example"
        if "VN_NEWS_RECOVERY_BUCKET=" not in env_template.read_text(encoding="utf-8"):
            raise ValueError(f"{env_template} must configure VN_NEWS_RECOVERY_BUCKET")


def terraform_local_string(text: str, name: str) -> str:
    match = re.search(rf'^\s*{re.escape(name)}\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    if not match:
        raise ValueError(f"terraform/oci/locals.tf missing string local: {name}")
    return match.group(1)


def terraform_local_set(text: str, name: str) -> set[str]:
    match = re.search(
        rf"^\s*{re.escape(name)}\s*=\s*toset\(\[(?P<body>.*?)\]\)\s*$",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise ValueError(f"terraform/oci/locals.tf missing toset local: {name}")
    return set(re.findall(r'"([^"]+)"', match.group("body")))


def validate_pipeline_metrics(config: dict) -> None:
    metrics = config["event_bus"].get("metrics")
    if not metrics:
        raise ValueError("event_bus.metrics must be configured")
    processing = load_compose("compose.processing.yaml")
    pipeline_metrics = processing["services"].get("pipeline-metrics")
    if pipeline_metrics is None:
        raise ValueError("processing Compose must run pipeline-metrics")
    if pipeline_metrics.get("secrets"):
        raise ValueError("pipeline-metrics must not mount storage credentials")
    healthcheck = pipeline_metrics.get("healthcheck", {}).get("test", [])
    if "landing_storage" in healthcheck or "event_bus,schema_registry" not in healthcheck:
        raise ValueError("pipeline-metrics healthcheck must exclude landing_storage")

    locals_text = (INFRA_ROOT / "terraform" / "oci" / "locals.tf").read_text(encoding="utf-8")
    if terraform_local_string(locals_text, "metric_namespace") != metrics["namespace"]:
        raise ValueError("Terraform metric_namespace must match event_bus.metrics.namespace")
    if terraform_local_set(locals_text, "pipeline_consumer_groups") != set(
        metrics["consumer_lag_groups"]
    ):
        raise ValueError(
            "Terraform pipeline_consumer_groups must match event_bus.metrics.consumer_lag_groups"
        )


def validate_event_contracts(config: dict) -> None:
    configured_topics = set(config["event_bus"]["topics"])
    contract_topic_keys = set(EVENT_TOPIC_KEYS)
    missing_contracts = configured_topics - contract_topic_keys
    if missing_contracts:
        msg = f"Configured topics missing event contracts: {sorted(missing_contracts)}"
        raise ValueError(msg)
    orphan_contracts = contract_topic_keys - configured_topics
    if orphan_contracts:
        msg = f"Event contracts are not configured as topics: {sorted(orphan_contracts)}"
        raise ValueError(msg)
    for topic_key, event_name in EVENT_TOPIC_KEYS.items():
        if event_name not in EVENT_CONTRACTS:
            msg = f"Topic {topic_key} references missing event contract: {event_name}"
            raise ValueError(msg)


def main() -> None:
    validate_release_manifests()
    validate_workflow_action_pins()
    config = load_settings()
    sources = load_sources(settings=config)
    enabled_sources = [source for source in sources if source["enabled"]]
    enabled_feeds = sum(len(source["feed_discovery"]["feeds"]) for source in enabled_sources)
    validate_settings_consistency(config)
    validate_platform_services(config)
    validate_cloudflare_access()
    validate_compose_healthchecks()
    validate_release_identity_usage()
    validate_recovery_controls()
    validate_pipeline_metrics(config)
    validate_source_filenames()
    validate_platform_lib_package()
    validate_uv_projects()
    validate_app()
    validate_services()
    validate_orchestration()
    validate_image_catalog()
    validate_event_contracts(config)
    print(
        "workspace validation ok: "
        f"{len(enabled_sources)}/{len(sources)} sources enabled, "
        f"{enabled_feeds} feeds configured"
    )


if __name__ == "__main__":
    main()
