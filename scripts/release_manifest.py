from __future__ import annotations

import argparse
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from scripts.release_tags import validate_tag

CICD_ROOT = Path(__file__).resolve().parents[1]
RELEASES_ROOT = CICD_ROOT / "releases"
COMMIT_REF_PATTERN = re.compile(r"[0-9a-f]{40}")
REQUIRED_REPOSITORIES = (
    "vn-news-cicd",
    "vn-news-app",
    "vn-news-config",
    "vn-news-infra",
    "vn-news-orchestration",
    "vn-news-platform-lib",
    "vn-news-services",
)


@dataclass(frozen=True)
class ReleaseManifest:
    release_tag: str
    image_tag: str
    repositories: dict[str, str]


def load_release_manifest(path: Path) -> ReleaseManifest:
    with path.open("rb") as manifest_file:
        manifest = tomllib.load(manifest_file)

    if manifest.get("version") != 1:
        raise ValueError(f"{path} version must be 1")

    release_tag = manifest.get("release_tag")
    if not isinstance(release_tag, str):
        raise ValueError(f"{path} must define release_tag")
    validate_tag(release_tag, push=True)
    image_tag = manifest.get("image_tag", release_tag)
    if not isinstance(image_tag, str):
        raise ValueError(f"{path} image_tag must be a string")
    validate_tag(image_tag, push=True)

    repositories = manifest.get("repositories")
    if not isinstance(repositories, dict):
        raise ValueError(f"{path} must define repositories")

    expected = set(REQUIRED_REPOSITORIES)
    actual = set(repositories)
    if actual != expected:
        raise ValueError(f"{path} repositories must be {sorted(expected)}, got {sorted(actual)}")
    for repository, commit_ref in repositories.items():
        if not isinstance(commit_ref, str) or not COMMIT_REF_PATTERN.fullmatch(commit_ref):
            raise ValueError(f"{path} repository {repository} must use a full commit SHA")
    return ReleaseManifest(
        release_tag=release_tag,
        image_tag=image_tag,
        repositories=repositories,
    )


def resolve_release_manifest(filename: str) -> Path:
    path = (RELEASES_ROOT / filename).resolve()
    if path.parent != RELEASES_ROOT.resolve():
        raise ValueError("release manifest must be a file under releases/")
    return path


def write_github_output(manifest: ReleaseManifest, path: Path) -> None:
    lines = [
        f"release_tag={manifest.release_tag}",
        f"image_tag={manifest.image_tag}",
    ]
    lines.extend(
        f"{repository.replace('-', '_')}_ref={commit_ref}"
        for repository, commit_ref in sorted(manifest.repositories.items())
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a coordinated release manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = load_release_manifest(resolve_release_manifest(args.manifest))
    if args.github_output:
        write_github_output(manifest, args.github_output)
    print(
        f"release manifest ok: {args.manifest} -> "
        f"release={manifest.release_tag}, image={manifest.image_tag}"
    )


if __name__ == "__main__":
    main()
