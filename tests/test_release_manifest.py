from __future__ import annotations

from pathlib import Path

import pytest
from scripts.release_manifest import (
    REQUIRED_REPOSITORIES,
    ReleaseManifest,
    load_release_manifest,
    write_github_output,
)


def write_manifest(path: Path, repositories: dict[str, str]) -> None:
    repository_lines = "\n".join(
        f'{repository} = "{commit_ref}"' for repository, commit_ref in repositories.items()
    )
    path.write_text(
        f'version = 1\nrelease_tag = "0.1.0"\n\n[repositories]\n{repository_lines}\n',
        encoding="utf-8",
    )


def test_release_manifest_accepts_full_commit_refs(tmp_path: Path) -> None:
    path = tmp_path / "release.toml"
    repositories = {
        repository: f"{index:x}" * 40
        for index, repository in enumerate(REQUIRED_REPOSITORIES, start=1)
    }
    write_manifest(path, repositories)

    manifest = load_release_manifest(path)

    assert manifest == ReleaseManifest(
        release_tag="0.1.0",
        image_tag="0.1.0",
        repositories=repositories,
    )


def test_release_manifest_accepts_separate_image_tag(tmp_path: Path) -> None:
    path = tmp_path / "release.toml"
    repositories = {repository: "a" * 40 for repository in REQUIRED_REPOSITORIES}
    write_manifest(path, repositories)
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace('release_tag = "0.1.0"', 'release_tag = "0.1.1"\nimage_tag = "0.1.0"'),
        encoding="utf-8",
    )

    manifest = load_release_manifest(path)

    assert manifest.release_tag == "0.1.1"
    assert manifest.image_tag == "0.1.0"


def test_release_manifest_requires_every_repository(tmp_path: Path) -> None:
    path = tmp_path / "release.toml"
    write_manifest(path, {REQUIRED_REPOSITORIES[0]: "a" * 40})

    with pytest.raises(ValueError, match="repositories must be"):
        load_release_manifest(path)


def test_release_manifest_rejects_short_commit_ref(tmp_path: Path) -> None:
    path = tmp_path / "release.toml"
    repositories = {repository: "a" * 40 for repository in REQUIRED_REPOSITORIES}
    repositories[REQUIRED_REPOSITORIES[0]] = "abc123"
    write_manifest(path, repositories)

    with pytest.raises(ValueError, match="full commit SHA"):
        load_release_manifest(path)


def test_github_output_uses_checkout_keys(tmp_path: Path) -> None:
    path = tmp_path / "github-output"
    manifest = ReleaseManifest(
        release_tag="0.1.0",
        image_tag="0.1.0",
        repositories={
            "vn-news-app": "a" * 40,
            "vn-news-platform-lib": "b" * 40,
        },
    )

    write_github_output(manifest, path)

    assert path.read_text(encoding="utf-8") == (
        "release_tag=0.1.0\n"
        "image_tag=0.1.0\n"
        f"vn_news_app_ref={'a' * 40}\n"
        f"vn_news_platform_lib_ref={'b' * 40}\n"
    )
