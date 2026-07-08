from __future__ import annotations

from pathlib import Path

import pytest
from scripts.deploy import refs


def test_parse_ref_overrides_accepts_cli_and_text_entries() -> None:
    overrides = refs.parse_ref_overrides(
        ["vn-news-app=main"],
        "vn-news-config=stable\nvn-news-infra=0123456789abcdef0123456789abcdef01234567",
    )

    assert overrides == {
        "vn-news-app": "main",
        "vn-news-config": "stable",
        "vn-news-infra": "0123456789abcdef0123456789abcdef01234567",
    }


def test_parse_ref_overrides_rejects_unknown_repository() -> None:
    with pytest.raises(ValueError, match="Unknown repository override"):
        refs.parse_ref_overrides(["unknown=main"], "")


def test_commit_ref_detection_accepts_uppercase_sha() -> None:
    assert refs.is_commit_ref("A" * 40)


def test_image_tag_from_manifest_accepts_explicit_tag() -> None:
    assert refs.image_tag_from_manifest("bundle-abc123", "") == "bundle-abc123"


def test_image_tag_from_manifest_accepts_json_manifest() -> None:
    assert (
        refs.image_tag_from_manifest("", '{"image_tag":"bundle-ed750e7c6400d6f3"}')
        == "bundle-ed750e7c6400d6f3"
    )


def test_image_tag_from_manifest_accepts_text_manifest() -> None:
    assert (
        refs.image_tag_from_manifest("", "image_tag=bundle-ed750e7c6400d6f3")
        == "bundle-ed750e7c6400d6f3"
    )


def test_resolve_deploy_refs_uses_explicit_image_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    commits = {
        repo_name: f"{index:040x}" for index, repo_name in enumerate(refs.REPOSITORIES, start=1)
    }

    def fake_resolve_remote_ref(owner: str, repo_name: str, ref: str) -> str:
        assert owner == "example"
        assert ref == "main"
        return commits[repo_name]

    monkeypatch.setattr(refs, "resolve_remote_ref", fake_resolve_remote_ref)

    image_tag, repositories = refs.resolve_deploy_refs(
        owner="example",
        default_ref="main",
        ref_overrides={},
        image_tag="sha-123",
        image_manifest="",
    )

    assert image_tag == "sha-123"
    assert repositories == commits


def test_resolve_deploy_refs_requires_existing_image_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commits = {
        repo_name: f"{index:040x}" for index, repo_name in enumerate(refs.REPOSITORIES, start=1)
    }

    monkeypatch.setattr(
        refs,
        "resolve_remote_ref",
        lambda _owner, repo_name, _ref: commits[repo_name],
    )

    with pytest.raises(ValueError, match="deploy does not build images"):
        refs.resolve_deploy_refs(
            owner="example",
            default_ref="main",
            ref_overrides={"vn-news-app": "feature"},
            image_tag="",
            image_manifest="",
        )


def test_write_github_output_uses_workflow_safe_names(tmp_path: Path) -> None:
    output_path = tmp_path / "github-output.txt"

    refs.write_github_output("bundle-abc", {"vn-news-app": "a" * 40}, output_path)

    assert output_path.read_text(encoding="utf-8").splitlines() == [
        "image_tag=bundle-abc",
        "vn_news_app_ref=" + ("a" * 40),
    ]
