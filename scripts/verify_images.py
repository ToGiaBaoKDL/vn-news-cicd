from __future__ import annotations

import argparse
import json
import subprocess

from scripts.image_catalog import image_reference, load_image_catalog
from scripts.release_tags import validate_tag


def manifest_platforms(manifest: dict) -> set[str]:
    platforms = set()
    for item in manifest.get("manifests", []):
        platform = item.get("platform", {})
        operating_system = platform.get("os")
        architecture = platform.get("architecture")
        if operating_system not in (None, "unknown") and architecture not in (None, "unknown"):
            platforms.add(f"{operating_system}/{architecture}")
    return platforms


def inspect_image(reference: str) -> dict:
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", "--raw", reference],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def verify_image(reference: str, required_platforms: set[str]) -> None:
    published_platforms = manifest_platforms(inspect_image(reference))
    missing_platforms = sorted(required_platforms - published_platforms)
    if missing_platforms:
        msg = f"{reference} is missing required platforms: {missing_platforms}"
        raise ValueError(msg)
    print(f"verified image: {reference} ({', '.join(sorted(published_platforms))})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify published images declared in images.yaml.")
    parser.add_argument("--image", action="append", dest="images")
    parser.add_argument("--tag", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_tag(args.tag, push=True)
    catalog = load_image_catalog()
    image_keys = args.images or sorted(catalog["images"])
    unknown_images = sorted(set(image_keys) - set(catalog["images"]))
    if unknown_images:
        raise ValueError(f"Unknown image keys: {unknown_images}")

    required_platforms = set(catalog["platforms"])
    for image_key in image_keys:
        verify_image(image_reference(catalog, image_key, args.tag), required_platforms)


if __name__ == "__main__":
    main()
