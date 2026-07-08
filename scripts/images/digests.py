from __future__ import annotations

import argparse
from pathlib import Path

from scripts.images.catalog import image_reference, image_repository_ref, load_image_catalog
from scripts.images.imagetools import resolve_digest
from scripts.images.manifest import compact_image_manifest
from scripts.images.tags import validate_tag


def image_digest_ref(catalog: dict, image_key: str, tag: str) -> str:
    tagged_reference = image_reference(catalog, image_key, tag)
    return f"{image_repository_ref(catalog, image_key)}@{resolve_digest(tagged_reference)}"


def digest_manifest(catalog: dict, tag: str, image_keys: list[str] | None = None) -> dict[str, str]:
    validate_tag(tag, push=True)
    selected_images = image_keys or sorted(catalog["images"])
    unknown_images = sorted(set(selected_images) - set(catalog["images"]))
    if unknown_images:
        raise ValueError(f"Unknown image keys: {unknown_images}")
    return {image_key: image_digest_ref(catalog, image_key, tag) for image_key in selected_images}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve pushed image tags to digest refs.")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--image", action="append", dest="images")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog = load_image_catalog(args.catalog)
    print(compact_image_manifest(digest_manifest(catalog, args.tag, args.images)))


if __name__ == "__main__":
    main()
