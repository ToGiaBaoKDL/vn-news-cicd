from __future__ import annotations

import argparse
import json
import os
import re
import shlex
from json import JSONDecodeError
from pathlib import Path

from scripts.images.catalog import (
    image_env,
    image_repository_ref,
    image_roles,
    load_image_catalog,
)

DIGEST_REF_PATTERN = re.compile(r"^.+@sha256:[a-f0-9]{64}$")


def parse_json_manifest(manifest: str) -> dict[str, str]:
    try:
        payload = json.loads(manifest)
    except JSONDecodeError as error:
        raise ValueError("image_manifest must be JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("image_manifest JSON must be an object")
    image_refs = payload
    if not isinstance(image_refs, dict):
        raise ValueError("image_manifest image refs must be an object")
    if not all(
        isinstance(image_key, str) and isinstance(image_ref, str)
        for image_key, image_ref in image_refs.items()
    ):
        raise ValueError("image_manifest image keys and refs must be strings")
    return image_refs


def parse_image_manifest(
    manifest: str,
    catalog: dict,
    *,
    require_complete: bool = True,
) -> dict[str, str]:
    normalized = manifest.strip()
    if not normalized:
        raise ValueError("image_manifest is required; deploy does not build images")

    image_refs = parse_json_manifest(normalized)
    required_images = set(catalog["images"])
    supplied_images = set(image_refs)
    missing = sorted(required_images - supplied_images)
    extra = sorted(supplied_images - required_images)
    if require_complete and missing:
        raise ValueError(f"image_manifest is missing image keys: {missing}")
    if extra:
        raise ValueError(f"image_manifest contains unknown image keys: {extra}")

    for image_key, image_ref in image_refs.items():
        validate_image_ref(catalog, image_key, image_ref)
    return {image_key: image_refs[image_key] for image_key in sorted(image_refs)}


def compact_image_manifest(image_refs: dict[str, str]) -> str:
    return json.dumps(dict(sorted(image_refs.items())), separators=(",", ":"))


def validate_image_ref(catalog: dict, image_key: str, image_ref: str) -> None:
    expected_repository = image_repository_ref(catalog, image_key)
    if image_ref.startswith(f"{expected_repository}:"):
        raise ValueError(f"{image_key} image ref must be digest-pinned")
    if not image_ref.startswith(f"{expected_repository}@sha256:"):
        raise ValueError(f"{image_key} image ref must start with {expected_repository}@sha256:")
    if not DIGEST_REF_PATTERN.fullmatch(image_ref):
        raise ValueError(f"{image_key} image ref must be digest-pinned")


def shell_exports(catalog: dict, image_refs: dict[str, str], role: str | None = None) -> str:
    values = {"VN_NEWS_IMAGE_MANIFEST": compact_image_manifest(image_refs)}
    for image_key, image_ref in image_refs.items():
        roles = image_roles(catalog, image_key)
        if role is None or role in roles:
            values[image_env(catalog, image_key)] = image_ref
    return "".join(f"export {key}={shlex.quote(value)}\n" for key, value in sorted(values.items()))


def cleanup_env_names(catalog: dict) -> str:
    names = sorted(image_env(catalog, key) for key in catalog["images"])
    return "".join(f"{name}\n" for name in names)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse and render deployment image manifests.")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--manifest", default=os.environ.get("VN_NEWS_IMAGE_MANIFEST", ""))
    parser.add_argument(
        "--format",
        choices=("json", "shell", "cleanup-env-names"),
        default="json",
    )
    parser.add_argument("--role", choices=("data", "control", "processing"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog = load_image_catalog(args.catalog)
    if args.format == "cleanup-env-names":
        print(cleanup_env_names(catalog), end="")
        return

    image_refs = parse_image_manifest(args.manifest, catalog)
    if args.format == "json":
        print(compact_image_manifest(image_refs))
    else:
        print(shell_exports(catalog, image_refs, role=args.role), end="")


if __name__ == "__main__":
    main()
