from __future__ import annotations

import argparse
import json
import os
import shlex
from pathlib import Path

from scripts.images.catalog import (
    catalog_value,
    image_owners,
    load_image_catalog,
    owner_source_repositories,
    owner_tag_env,
)
from scripts.images.tags import validate_tag


def parse_text_manifest(manifest: str) -> dict[str, str]:
    entries = [
        entry.strip()
        for chunk in manifest.splitlines()
        for entry in chunk.split(",")
        if entry.strip()
    ]
    image_tags: dict[str, str] = {}
    for entry in entries:
        if "=" in entry:
            owner, tag = entry.split("=", maxsplit=1)
        elif ":" in entry:
            owner, tag = entry.split(":", maxsplit=1)
        else:
            raise ValueError(f"Invalid image_manifest entry: {entry}")
        image_tags[owner.strip()] = tag.strip()
    return image_tags


def parse_json_manifest(manifest: str) -> dict[str, str]:
    payload = json.loads(manifest)
    if not isinstance(payload, dict):
        raise ValueError("image_manifest JSON must be an object")
    image_tags = payload.get("image_tags", payload)
    if not isinstance(image_tags, dict):
        raise ValueError("image_manifest image_tags must be an object")
    if not all(
        isinstance(owner, str) and isinstance(tag, str) for owner, tag in image_tags.items()
    ):
        raise ValueError("image_manifest owners and tags must be strings")
    return image_tags


def parse_image_manifest(manifest: str, catalog: dict) -> dict[str, str]:
    normalized = manifest.strip()
    if not normalized:
        raise ValueError("image_manifest is required; deploy does not build images")

    image_tags = (
        parse_json_manifest(normalized)
        if normalized.startswith("{")
        else parse_text_manifest(normalized)
    )
    required_owners = set(image_owners(catalog))
    supplied_owners = set(image_tags)
    missing = sorted(required_owners - supplied_owners)
    extra = sorted(supplied_owners - required_owners)
    if missing:
        raise ValueError(f"image_manifest is missing image owners: {missing}")
    if extra:
        raise ValueError(f"image_manifest contains unknown image owners: {extra}")

    for tag in image_tags.values():
        validate_tag(tag, push=True)
    return {owner: image_tags[owner] for owner in sorted(image_tags)}


def compact_image_manifest(image_tags: dict[str, str]) -> str:
    return json.dumps(dict(sorted(image_tags.items())), separators=(",", ":"))


def expected_owner_tag(owner: str, catalog: dict, repositories: dict[str, str]) -> str:
    parts: list[str] = []
    for repo_name in owner_source_repositories(catalog, owner):
        commit_ref = repositories.get(repo_name, "")
        if len(commit_ref) < 12:
            raise ValueError(f"Cannot derive image tag for {owner}; missing ref for {repo_name}")
        parts.append(commit_ref[:12].lower())
    return "sha-" + "-".join(parts)


def validate_image_manifest_refs(
    image_tags: dict[str, str],
    catalog: dict,
    repositories: dict[str, str],
) -> None:
    for owner in image_owners(catalog):
        expected_tag = expected_owner_tag(owner, catalog, repositories)
        actual_tag = image_tags[owner]
        if actual_tag != expected_tag:
            raise ValueError(
                f"{owner} image tag must be {expected_tag} for the resolved refs, got {actual_tag}"
            )


def shell_exports(catalog: dict, image_tags: dict[str, str]) -> str:
    values = {
        "VN_NEWS_IMAGE_MANIFEST": compact_image_manifest(image_tags),
        "VN_NEWS_IMAGE_NAMESPACE": catalog_value(catalog, "namespace", "VN_NEWS_IMAGE_NAMESPACE"),
        "VN_NEWS_IMAGE_REGISTRY": catalog_value(catalog, "registry", "VN_NEWS_IMAGE_REGISTRY"),
    }
    values.update({owner_tag_env(catalog, owner): tag for owner, tag in image_tags.items()})
    return "".join(f"export {key}={shlex.quote(value)}\n" for key, value in sorted(values.items()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse and render deployment image manifests.")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--manifest", default=os.environ.get("VN_NEWS_IMAGE_MANIFEST", ""))
    parser.add_argument("--format", choices=("json", "shell"), default="json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog = load_image_catalog(args.catalog)
    image_tags = parse_image_manifest(args.manifest, catalog)
    if args.format == "json":
        print(compact_image_manifest(image_tags))
    else:
        print(shell_exports(catalog, image_tags), end="")


if __name__ == "__main__":
    main()
