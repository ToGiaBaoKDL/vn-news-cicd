from __future__ import annotations

import os
from pathlib import Path

import yaml

from scripts.paths import CICD_ROOT


def load_image_catalog(path: Path | None = None) -> dict:
    catalog_path = path or CICD_ROOT / "images.yaml"
    return yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}


def catalog_value(catalog: dict, field: str, env_name: str) -> str:
    value = catalog.get(field) or os.environ.get(env_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Image catalog must define {field} or {env_name}")
    return value.strip()


def image_reference(catalog: dict, image_key: str, tag: str) -> str:
    return f"{image_repository_ref(catalog, image_key)}:{tag}"


def image_repository_ref(catalog: dict, image_key: str) -> str:
    image = catalog["images"][image_key]
    registry = catalog_value(catalog, "registry", "VN_NEWS_IMAGE_REGISTRY")
    namespace = catalog_value(catalog, "namespace", "VN_NEWS_IMAGE_NAMESPACE")
    return f"{registry}/{namespace}/{image['image_repository']}"


def image_owner(catalog: dict, image_key: str) -> str:
    owner = catalog["images"][image_key].get("owner")
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError(f"Image {image_key} is missing owner")
    return owner.strip()


def image_owners(catalog: dict) -> tuple[str, ...]:
    owners = catalog.get("owners")
    if isinstance(owners, dict) and owners:
        return tuple(sorted(owners))
    return tuple(sorted({image_owner(catalog, image_key) for image_key in catalog["images"]}))


def owner_source_repositories(catalog: dict, owner: str) -> tuple[str, ...]:
    owners = catalog.get("owners", {})
    source_repositories = (
        owners.get(owner, {}).get("source_repositories") if isinstance(owners, dict) else None
    )
    if not isinstance(source_repositories, list) or not source_repositories:
        raise ValueError(f"Image owner {owner} is missing source_repositories")
    return tuple(str(repository) for repository in source_repositories)


def image_env(catalog: dict, image_key: str) -> str:
    value = catalog["images"][image_key].get("image_env")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Image {image_key} is missing image_env")
    return value.strip()


def image_roles(catalog: dict, image_key: str) -> tuple[str, ...]:
    roles = catalog["images"][image_key].get("roles", [])
    if not isinstance(roles, list):
        raise ValueError(f"Image {image_key} roles must be a list")
    return tuple(str(role) for role in roles)
