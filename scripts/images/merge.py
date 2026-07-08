from __future__ import annotations

import argparse
from pathlib import Path

from scripts.images.catalog import load_image_catalog
from scripts.images.manifest import compact_image_manifest, parse_image_manifest


def merge_image_manifests(
    base_manifest: str,
    update_manifest: str,
    catalog: dict,
) -> dict[str, str]:
    base_refs = parse_image_manifest(base_manifest, catalog)
    update_refs = parse_image_manifest(update_manifest, catalog, require_complete=False)
    return dict(sorted({**base_refs, **update_refs}.items()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge partial image refs into a full manifest.")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--base", required=True)
    parser.add_argument("--update", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog = load_image_catalog(args.catalog)
    print(compact_image_manifest(merge_image_manifests(args.base, args.update, catalog)))


if __name__ == "__main__":
    main()
