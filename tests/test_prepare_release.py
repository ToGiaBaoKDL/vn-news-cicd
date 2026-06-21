from __future__ import annotations

from pathlib import Path

import pytest
from scripts.release import prepare as prepare_release
from scripts.release.manifest import REQUIRED_REPOSITORIES, load_release_manifest


def test_parse_ref_overrides_accepts_cli_and_text_refs() -> None:
    overrides = prepare_release.parse_ref_overrides(
        ["vn-news-services=feature/ref"],
        "vn-news-orchestration=main\nvn-news-config=abc123",
    )

    assert overrides == {
        "vn-news-config": "abc123",
        "vn-news-orchestration": "main",
        "vn-news-services": "feature/ref",
    }


def test_parse_ref_overrides_rejects_unknown_repo() -> None:
    with pytest.raises(ValueError, match="Unknown release repository"):
        prepare_release.parse_ref_overrides(["vn-news-unknown=main"], "")


def test_prepare_release_writes_full_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commits = {
        repo_name: f"{index:x}" * 40 for index, repo_name in enumerate(REQUIRED_REPOSITORIES, 1)
    }
    resolved_refs: list[tuple[str, str, str]] = []

    def fake_resolve_remote_ref(owner: str, repo_name: str, ref: str) -> str:
        resolved_refs.append((owner, repo_name, ref))
        return commits[repo_name]

    monkeypatch.setattr(prepare_release, "RELEASES_ROOT", tmp_path)
    monkeypatch.setattr(prepare_release, "resolve_remote_ref", fake_resolve_remote_ref)

    path = prepare_release.prepare_release(
        release_tag="0.3.0",
        image_tag="0.2.7",
        default_ref="main",
        owner="ToGiaBaoKDL",
        ref_overrides={"vn-news-orchestration": "dag-fix"},
        output=None,
        overwrite=False,
    )

    manifest = load_release_manifest(path)

    assert path == tmp_path / "0.3.0.toml"
    assert manifest.release_tag == "0.3.0"
    assert manifest.image_tag == "0.2.7"
    assert manifest.repositories == commits
    assert ("ToGiaBaoKDL", "vn-news-orchestration", "dag-fix") in resolved_refs
    assert ("ToGiaBaoKDL", "vn-news-services", "main") in resolved_refs


def test_prepare_release_refuses_existing_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(prepare_release, "RELEASES_ROOT", tmp_path)
    (tmp_path / "0.3.0.toml").write_text("", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        prepare_release.prepare_release(
            release_tag="0.3.0",
            image_tag="0.3.0",
            default_ref="main",
            owner="ToGiaBaoKDL",
            ref_overrides={},
            output=None,
            overwrite=False,
        )
