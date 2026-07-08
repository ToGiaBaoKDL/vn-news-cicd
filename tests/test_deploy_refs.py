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


def test_remote_ref_candidates_use_branch_names_by_default() -> None:
    assert refs.remote_ref_candidates("main") == ("refs/heads/main",)
    with pytest.raises(ValueError, match="non-tag refs"):
        refs.remote_ref_candidates("refs/tags/v1")


def test_image_manifest_rejects_bare_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(refs, "resolve_remote_ref", lambda _owner, _repo_name, _ref: "a" * 40)

    with pytest.raises(ValueError, match="image_manifest must be JSON"):
        refs.resolve_deploy_refs(
            owner="example",
            default_ref="main",
            ref_overrides={},
            image_manifest="bundle-ed750e7c6400d6f3",
        )


def test_resolve_deploy_refs_uses_image_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    commits = {repo_name: str(index) * 40 for index, repo_name in enumerate(refs.REPOSITORIES, 1)}

    def fake_resolve_remote_ref(owner: str, repo_name: str, ref: str) -> str:
        assert owner == "example"
        assert ref == "main"
        return commits[repo_name]

    monkeypatch.setattr(refs, "resolve_remote_ref", fake_resolve_remote_ref)

    image_tags, repositories = refs.resolve_deploy_refs(
        owner="example",
        default_ref="main",
        ref_overrides={},
        image_manifest=(
            '{"vn-news-app":"sha-111111111111-777777777777",'
            '"vn-news-infra":"sha-444444444444",'
            '"vn-news-services":"sha-888888888888-777777777777"}'
        ),
    )

    assert image_tags == {
        "vn-news-app": "sha-111111111111-777777777777",
        "vn-news-infra": "sha-444444444444",
        "vn-news-services": "sha-888888888888-777777777777",
    }
    assert repositories == commits


def test_resolve_deploy_refs_rejects_mismatched_image_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commits = {repo_name: str(index) * 40 for index, repo_name in enumerate(refs.REPOSITORIES, 1)}

    monkeypatch.setattr(
        refs,
        "resolve_remote_ref",
        lambda _owner, repo_name, _ref: commits[repo_name],
    )

    with pytest.raises(ValueError, match="vn-news-app image tag must be"):
        refs.resolve_deploy_refs(
            owner="example",
            default_ref="main",
            ref_overrides={"vn-news-app": "feature"},
            image_manifest=(
                '{"vn-news-app":"sha-wrong",'
                '"vn-news-infra":"sha-444444444444",'
                '"vn-news-services":"sha-888888888888-777777777777"}'
            ),
        )


def test_write_github_output_uses_workflow_safe_names(tmp_path: Path) -> None:
    output_path = tmp_path / "github-output.txt"

    refs.write_github_output(
        {"vn-news-app": "sha-a", "vn-news-infra": "sha-b"},
        {"vn-news-app": "a" * 40},
        output_path,
    )

    assert output_path.read_text(encoding="utf-8").splitlines() == [
        'image_manifest={"vn-news-app":"sha-a","vn-news-infra":"sha-b"}',
        "vn_news_app_ref=" + ("a" * 40),
    ]
