from __future__ import annotations

import subprocess

import pytest
from scripts.images.digests import digest_manifest, resolve_digest


def test_resolve_digest_reads_manifest_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="sha256:" + ("a" * 64) + "\n",
        )

    monkeypatch.setattr("scripts.images.imagetools.subprocess.run", fake_run)

    assert resolve_digest("docker.io/example/app:tag") == "sha256:" + ("a" * 64)


def test_digest_manifest_outputs_per_image_digest_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.images.digests.resolve_digest",
        lambda _reference: "sha256:" + ("b" * 64),
    )
    catalog = {
        "registry": "docker.io",
        "namespace": "example",
        "images": {
            "api": {"image_repository": "vn-news-api"},
            "web": {"image_repository": "vn-news-web"},
        },
    }

    assert digest_manifest(catalog, "sha-app", ["api"]) == {
        "api": "docker.io/example/vn-news-api@sha256:" + ("b" * 64)
    }
