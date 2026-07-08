from __future__ import annotations

import re
from pathlib import Path

from scripts.workspace.common import (
    APP_ROOT,
    CICD_ROOT,
    DEPLOY_ROLES,
    INFRA_ROOT,
    REPOSITORY_NAMES,
    SERVICES_ROOT,
    WORKSPACE_ROOT,
    duplicate_values,
    load_yaml,
)

SOURCE_IMAGE_CATALOGS = {
    "vn-news-app": APP_ROOT,
    "vn-news-infra": INFRA_ROOT,
    "vn-news-services": SERVICES_ROOT,
}


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

    duplicates = duplicate_values(repositories)
    if duplicates:
        raise ValueError(f"Duplicate Docker image repositories in images.yaml: {duplicates}")
    duplicate_image_envs = duplicate_values(image_envs)
    if duplicate_image_envs:
        raise ValueError(f"Duplicate image env variables in images.yaml: {duplicate_image_envs}")

    validate_source_image_catalogs(catalog, images_by_owner)


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
        "PUBLISH_IMAGE_TAG",
        "Resolve publish image tag",
        "steps.images.outputs.has_changes",
        "steps.images.outputs.image_args",
    )
    for fragment in required_fragments:
        if fragment not in workflow:
            raise ValueError(f"{workflow_path} missing image publish fragment: {fragment}")
    legacy_image_tag_patterns = (
        re.compile(r"(?m)^\s*IMAGE_TAG:"),
        re.compile(r"\$(?:\{)?IMAGE_TAG(?:\}|[\s\"')])"),
    )
    if any(pattern.search(workflow) for pattern in legacy_image_tag_patterns):
        raise ValueError(f"{workflow_path} must use PUBLISH_IMAGE_TAG, not IMAGE_TAG")
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
