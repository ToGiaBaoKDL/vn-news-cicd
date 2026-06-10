from __future__ import annotations

import pytest
from scripts.image_catalog import image_reference
from scripts.verify_images import manifest_platforms, verify_image


def test_image_reference_uses_catalog_identity() -> None:
    catalog = {
        "registry": "docker.io",
        "namespace": "example",
        "images": {"worker": {"image_repository": "vn-news-worker"}},
    }

    assert image_reference(catalog, "worker", "0.3.0") == "docker.io/example/vn-news-worker:0.3.0"


def test_manifest_platforms_reads_image_index() -> None:
    manifest = {
        "manifests": [
            {"platform": {"os": "linux", "architecture": "amd64"}},
            {"platform": {"os": "linux", "architecture": "arm64"}},
            {"platform": {"os": "unknown", "architecture": "unknown"}},
        ]
    }

    assert manifest_platforms(manifest) == {"linux/amd64", "linux/arm64"}


def test_verify_image_rejects_missing_platform(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.verify_images.inspect_image",
        lambda _: {"manifests": [{"platform": {"os": "linux", "architecture": "amd64"}}]},
    )

    with pytest.raises(ValueError, match="linux/arm64"):
        verify_image("docker.io/example/worker:0.3.0", {"linux/amd64", "linux/arm64"})
