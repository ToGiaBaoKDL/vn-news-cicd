from __future__ import annotations

import pytest
from scripts.images import artifacts


def test_resolve_manifest_run_ids_discovers_missing_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_latest_artifact_run_id(**kwargs) -> str:
        calls.append(kwargs["repo"])
        return f"run-{kwargs['repo']}"

    monkeypatch.setattr(artifacts, "latest_artifact_run_id", fake_latest_artifact_run_id)

    assert artifacts.resolve_manifest_run_ids(
        owner="owner",
        branch="main",
        workflow_name="Publish Images",
        artifact_name="image-manifest",
        token="token",
        provided_run_ids={"app": "123", "infra": "", "services": ""},
    ) == {
        "app": "123",
        "infra": "run-vn-news-infra",
        "services": "run-vn-news-services",
    }
    assert calls == ["vn-news-infra", "vn-news-services"]


def test_resolve_manifest_run_ids_does_not_discover_for_base_promotion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        artifacts,
        "latest_artifact_run_id",
        lambda **_kwargs: pytest.fail("should not auto-discover with a base manifest"),
    )

    assert artifacts.resolve_manifest_run_ids(
        owner="owner",
        branch="main",
        workflow_name="Publish Images",
        artifact_name="image-manifest",
        token="token",
        provided_run_ids={"app": "", "infra": "", "services": "456"},
        base_run_id="789",
    ) == {"app": "", "infra": "", "services": "456"}


def test_run_has_artifact_ignores_expired_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        artifacts,
        "api_get",
        lambda _url, _token: {
            "artifacts": [
                {"name": "image-manifest", "expired": True},
                {"name": "other", "expired": False},
            ]
        },
    )

    assert not artifacts.run_has_artifact(
        owner="owner",
        repo="repo",
        run_id=123,
        artifact_name="image-manifest",
        token="token",
    )


def test_resolve_manifest_run_ids_rejects_manual_with_artifacts() -> None:
    with pytest.raises(ValueError, match="manual image_manifest"):
        artifacts.resolve_manifest_run_ids(
            owner="owner",
            branch="main",
            workflow_name="Publish Images",
            artifact_name="image-manifest",
            token="token",
            provided_run_ids={"app": "123", "infra": "", "services": ""},
            manual_manifest='{"app":"ref"}',
        )


def test_resolve_manifest_run_ids_rejects_duplicate_base_sources() -> None:
    with pytest.raises(ValueError, match="one base manifest source"):
        artifacts.resolve_manifest_run_ids(
            owner="owner",
            branch="main",
            workflow_name="Publish Images",
            artifact_name="image-manifest",
            token="token",
            provided_run_ids={"app": "", "infra": "", "services": ""},
            base_manifest='{"app":"ref"}',
            base_run_id="456",
        )
