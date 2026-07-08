from __future__ import annotations

import pytest
from scripts.images.promote import promoted_image_manifest


def digest_ref(repository: str, digest: str) -> str:
    return f"docker.io/example/{repository}@sha256:{digest * 64}"


def catalog() -> dict:
    return {
        "registry": "docker.io",
        "namespace": "example",
        "images": {
            "api": {"image_repository": "vn-news-api"},
            "web": {"image_repository": "vn-news-web"},
            "worker": {"image_repository": "vn-news-worker"},
        },
    }


def test_promoted_manifest_merges_partial_updates_into_base() -> None:
    base = (
        '{"api":"'
        + digest_ref("vn-news-api", "a")
        + '","web":"'
        + digest_ref("vn-news-web", "b")
        + '","worker":"'
        + digest_ref("vn-news-worker", "c")
        + '"}'
    )
    update = '{"worker":"' + digest_ref("vn-news-worker", "d") + '"}'

    assert promoted_image_manifest(
        catalog=catalog(),
        base_manifest=base,
        update_manifests=(update,),
    ) == {
        "api": digest_ref("vn-news-api", "a"),
        "web": digest_ref("vn-news-web", "b"),
        "worker": digest_ref("vn-news-worker", "d"),
    }


def test_promoted_manifest_accepts_base_only_for_rollback() -> None:
    base = (
        '{"api":"'
        + digest_ref("vn-news-api", "a")
        + '","web":"'
        + digest_ref("vn-news-web", "b")
        + '","worker":"'
        + digest_ref("vn-news-worker", "c")
        + '"}'
    )

    assert promoted_image_manifest(catalog=catalog(), base_manifest=base) == {
        "api": digest_ref("vn-news-api", "a"),
        "web": digest_ref("vn-news-web", "b"),
        "worker": digest_ref("vn-news-worker", "c"),
    }


def test_promoted_manifest_accepts_complete_artifact_set_without_base() -> None:
    app = '{"api":"' + digest_ref("vn-news-api", "a") + '"}'
    web = '{"web":"' + digest_ref("vn-news-web", "b") + '"}'
    worker = '{"worker":"' + digest_ref("vn-news-worker", "c") + '"}'

    assert promoted_image_manifest(
        catalog=catalog(),
        update_manifests=(app, web, worker),
    ) == {
        "api": digest_ref("vn-news-api", "a"),
        "web": digest_ref("vn-news-web", "b"),
        "worker": digest_ref("vn-news-worker", "c"),
    }


def test_promoted_manifest_rejects_duplicate_updates() -> None:
    update = '{"api":"' + digest_ref("vn-news-api", "a") + '"}'

    with pytest.raises(ValueError, match="duplicate image refs"):
        promoted_image_manifest(
            catalog=catalog(),
            update_manifests=(update, update),
        )
