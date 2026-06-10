from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path

import yaml

from scripts.release_tags import validate_tag

CICD_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = CICD_ROOT.parent


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build images declared in images.yaml.")
    parser.add_argument("--github-actions-cache", action="store_true")
    parser.add_argument("--image", action="append", dest="images")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def image_command(
    catalog: dict,
    image_key: str,
    tag: str,
    push: bool,
    github_actions_cache: bool = False,
) -> list[str]:
    image = catalog["images"][image_key]
    build = image["build"]
    context = WORKSPACE_ROOT / build["context"]
    command = [
        "docker",
        "buildx",
        "build",
        "--file",
        str(context / build["dockerfile"]),
        "--tag",
        f"{catalog['registry']}/{catalog['namespace']}/{image['image_repository']}:{tag}",
    ]
    platforms = catalog.get("platforms", [])
    if push and platforms:
        command.extend(["--platform", ",".join(platforms)])
    if github_actions_cache:
        cache_scope = f"vn-news-{image_key}"
        command.extend(
            [
                "--cache-from",
                f"type=gha,scope={cache_scope}",
                "--cache-to",
                f"type=gha,mode=max,scope={cache_scope}",
            ]
        )
    for name, path in sorted(build.get("additional_contexts", {}).items()):
        command.extend(["--build-context", f"{name}={WORKSPACE_ROOT / path}"])
    command.append("--push" if push else "--load")
    command.append(str(context))
    return command


def main() -> None:
    args = parse_args()
    catalog = load_yaml(CICD_ROOT / "images.yaml")
    validate_tag(args.tag, push=args.push)
    image_keys = args.images or sorted(catalog["images"])
    unknown_images = sorted(set(image_keys) - set(catalog["images"]))
    if unknown_images:
        msg = f"Unknown image keys: {unknown_images}"
        raise ValueError(msg)

    for image_key in image_keys:
        command = image_command(
            catalog,
            image_key,
            args.tag,
            args.push,
            args.github_actions_cache,
        )
        print(shlex.join(command))
        if not args.dry_run:
            subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
