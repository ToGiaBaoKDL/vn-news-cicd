from __future__ import annotations

from pathlib import Path

import yaml

from scripts.paths import CICD_ROOT


def load_image_catalog(path: Path | None = None) -> dict:
    catalog_path = path or CICD_ROOT / "images.yaml"
    return yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}


def image_reference(catalog: dict, image_key: str, tag: str) -> str:
    image = catalog["images"][image_key]
    return f"{catalog['registry']}/{catalog['namespace']}/{image['image_repository']}:{tag}"
