from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from pathlib import Path

from scripts.images.catalog import load_image_catalog


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").removeprefix("./").strip("/")


def path_matches(pattern: str, path: str) -> bool:
    pattern = normalize_path(pattern)
    path = normalize_path(path)
    if not pattern or not path:
        return False
    if pattern.endswith("/**"):
        directory = pattern.removesuffix("/**")
        return path == directory or path.startswith(f"{directory}/")
    return fnmatch.fnmatchcase(path, pattern)


def changed_paths(repo_root: Path, base_ref: str, head_ref: str) -> tuple[str, ...]:
    command = ["git", "diff", "--name-only", base_ref, head_ref]
    result = subprocess.run(
        command,
        cwd=repo_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return tuple(path for path in result.stdout.splitlines() if path.strip())


def image_change_paths(catalog: dict, image_key: str) -> tuple[str, ...]:
    common_paths = catalog.get("change_paths", [])
    image_paths = catalog["images"][image_key].get("change_paths", [])
    if not isinstance(common_paths, list):
        raise ValueError("Image catalog change_paths must be a list")
    if not isinstance(image_paths, list) or not image_paths:
        raise ValueError(f"Image {image_key} is missing change_paths")
    return tuple(str(path) for path in [*common_paths, *image_paths])


def selected_images(
    catalog: dict,
    paths: tuple[str, ...],
    build_all: bool = False,
) -> tuple[str, ...]:
    image_keys = tuple(sorted(catalog["images"]))
    if build_all:
        return image_keys
    normalized_paths = tuple(normalize_path(path) for path in paths if normalize_path(path))
    if not normalized_paths:
        return ()
    return tuple(
        image_key
        for image_key in image_keys
        if any(
            path_matches(pattern, changed_path)
            for changed_path in normalized_paths
            for pattern in image_change_paths(catalog, image_key)
        )
    )


def image_args(image_keys: tuple[str, ...]) -> str:
    return " ".join(f"--image {image_key}" for image_key in image_keys)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select image builds from changed source paths.")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--changed-path", action="append", dest="changed_paths")
    parser.add_argument("--build-all", action="store_true")
    parser.add_argument("--format", choices=("json", "shell"), default="json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog = load_image_catalog(args.catalog)
    paths = tuple(args.changed_paths or ())
    if not args.build_all and not paths:
        if not args.base_ref:
            raise ValueError("--base-ref is required unless --build-all or --changed-path is used")
        paths = changed_paths(args.repo_root, args.base_ref, args.head_ref)
    images = selected_images(catalog, paths, build_all=args.build_all)
    output = {
        "has_changes": "true" if images else "false",
        "images": " ".join(images),
        "image_args": image_args(images),
    }
    if args.format == "shell":
        for key, value in output.items():
            print(f"{key}={value}")
        return
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
