from __future__ import annotations

import argparse
import re
import shlex
import subprocess
from pathlib import Path

import yaml

CICD_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = CICD_ROOT.parent
IMAGE_TAG_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build images declared in images.yaml.")
    parser.add_argument("--environment", default="local", choices=["local", "staging", "prod"])
    parser.add_argument("--image", action="append", dest="images")
    parser.add_argument("--tag")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def image_command(
    catalog: dict,
    image_key: str,
    tag: str,
    push: bool,
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
    for name, path in sorted(build.get("additional_contexts", {}).items()):
        command.extend(["--build-context", f"{name}={WORKSPACE_ROOT / path}"])
    command.append("--push" if push else "--load")
    command.append(str(context))
    return command


def validate_tag(tag: str, *, push: bool) -> None:
    if not IMAGE_TAG_PATTERN.fullmatch(tag):
        raise ValueError(f"Invalid Docker image tag: {tag}")
    if push and tag == "latest":
        raise ValueError("Published images must use an immutable release tag")


def main() -> None:
    args = parse_args()
    catalog = load_yaml(CICD_ROOT / "images.yaml")
    release = load_yaml(CICD_ROOT / "envs" / f"{args.environment}.yaml")
    tag = args.tag or release["tag"]
    validate_tag(tag, push=args.push)
    image_keys = args.images or sorted(catalog["images"])
    unknown_images = sorted(set(image_keys) - set(catalog["images"]))
    if unknown_images:
        msg = f"Unknown image keys: {unknown_images}"
        raise ValueError(msg)

    for image_key in image_keys:
        command = image_command(catalog, image_key, tag, args.push)
        print(shlex.join(command))
        if not args.dry_run:
            subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
