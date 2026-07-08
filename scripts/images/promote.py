from __future__ import annotations

import argparse
from pathlib import Path

from scripts.images.catalog import load_image_catalog
from scripts.images.manifest import compact_image_manifest, parse_image_manifest


def existing_manifest_files(paths: list[Path], directories: list[Path]) -> tuple[Path, ...]:
    files = [path for path in paths if path.is_file()]
    for directory in directories:
        if directory.is_dir():
            files.extend(sorted(directory.rglob("image-manifest.json")))
    return tuple(sorted(set(files)))


def read_optional_file(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def promoted_image_manifest(
    *,
    catalog: dict,
    manual_manifest: str = "",
    base_manifest: str = "",
    update_manifests: tuple[str, ...] = (),
) -> dict[str, str]:
    manual_manifest = manual_manifest.strip()
    base_manifest = base_manifest.strip()
    update_manifests = tuple(manifest.strip() for manifest in update_manifests if manifest.strip())

    if manual_manifest:
        if base_manifest or update_manifests:
            raise ValueError("manual image_manifest cannot be combined with promotion artifacts")
        return parse_image_manifest(manual_manifest, catalog)

    image_refs = parse_image_manifest(base_manifest, catalog) if base_manifest else {}
    updated_keys: set[str] = set()
    for update_manifest in update_manifests:
        update_refs = parse_image_manifest(update_manifest, catalog, require_complete=False)
        duplicate_keys = sorted(updated_keys & set(update_refs))
        if duplicate_keys:
            raise ValueError(f"duplicate image refs in promotion artifacts: {duplicate_keys}")
        updated_keys.update(update_refs)
        image_refs.update(update_refs)

    if not image_refs:
        raise ValueError(
            "promotion requires image_manifest or at least one image manifest artifact"
        )
    return parse_image_manifest(compact_image_manifest(image_refs), catalog)


def write_github_output(image_manifest: str, path: Path) -> None:
    path.write_text(f"image_manifest={image_manifest}\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote published image manifests.")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--manual", default="")
    parser.add_argument("--base", default="")
    parser.add_argument("--base-file", type=Path)
    parser.add_argument("--manifest-file", action="append", type=Path, default=[])
    parser.add_argument("--manifest-dir", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog = load_image_catalog(args.catalog)
    base_file_manifest = read_optional_file(args.base_file)
    if args.base.strip() and base_file_manifest:
        raise ValueError("Use only one base manifest source")

    manifest_files = existing_manifest_files(args.manifest_file, args.manifest_dir)
    image_refs = promoted_image_manifest(
        catalog=catalog,
        manual_manifest=args.manual,
        base_manifest=args.base or base_file_manifest,
        update_manifests=tuple(path.read_text(encoding="utf-8") for path in manifest_files),
    )
    image_manifest = compact_image_manifest(image_refs)

    if args.output:
        args.output.write_text(image_manifest + "\n", encoding="utf-8")
    if args.github_output:
        write_github_output(image_manifest, args.github_output)
    print(image_manifest)


if __name__ == "__main__":
    main()
