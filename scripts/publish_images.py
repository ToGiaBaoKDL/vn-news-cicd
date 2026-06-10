from __future__ import annotations

import argparse
import shlex
import subprocess

from scripts.build_images import image_command, load_yaml
from scripts.release_tags import validate_tag
from scripts.verify_images import CICD_ROOT, image_reference


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def retag_command(catalog: dict, image_key: str, from_tag: str, to_tag: str) -> list[str]:
    return [
        "docker",
        "buildx",
        "imagetools",
        "create",
        "--tag",
        image_reference(catalog, image_key, to_tag),
        image_reference(catalog, image_key, from_tag),
    ]


def run_command(command: list[str], *, dry_run: bool) -> None:
    print(shlex.join(command))
    if not dry_run:
        subprocess.run(command, check=True)


def publish_images(
    *,
    tag: str,
    from_tag: str,
    build_images: list[str],
    copy_images: list[str],
    push: bool,
    github_actions_cache: bool,
    dry_run: bool,
) -> None:
    catalog = load_yaml(CICD_ROOT / "images.yaml")
    validate_tag(tag, push=push)
    if from_tag:
        validate_tag(from_tag, push=True)

    image_keys = set(catalog["images"])
    selected = set(build_images) | set(copy_images)
    unknown_images = sorted(selected - image_keys)
    if unknown_images:
        raise ValueError(f"Unknown image keys: {unknown_images}")
    overlap = sorted(set(build_images) & set(copy_images))
    if overlap:
        raise ValueError(f"Images cannot be both built and copied: {overlap}")

    for image_key in build_images:
        command = image_command(
            catalog,
            image_key,
            tag,
            push,
            github_actions_cache,
        )
        run_command(command, dry_run=dry_run)

    if copy_images and not from_tag:
        raise ValueError("from_tag is required when copy_images is not empty")
    if copy_images and from_tag == tag:
        print("source and target tags are identical; skipping image copy")
        return
    for image_key in copy_images:
        run_command(retag_command(catalog, image_key, from_tag, tag), dry_run=dry_run)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build changed images and copy unchanged images.")
    parser.add_argument("--build-images", default="")
    parser.add_argument("--copy-images", default="")
    parser.add_argument("--from-tag", default="")
    parser.add_argument("--github-actions-cache", action="store_true")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    publish_images(
        tag=args.tag,
        from_tag=args.from_tag,
        build_images=parse_csv(args.build_images),
        copy_images=parse_csv(args.copy_images),
        push=args.push,
        github_actions_cache=args.github_actions_cache,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
