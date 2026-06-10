from __future__ import annotations

import pytest
from scripts.publish_images import parse_csv, publish_images, retag_command


def test_parse_csv_ignores_empty_items() -> None:
    assert parse_csv("app_api,, service_feed_ingestor ,") == [
        "app_api",
        "service_feed_ingestor",
    ]


def test_retag_command_uses_remote_manifest_copy() -> None:
    catalog = {
        "registry": "docker.io",
        "namespace": "example",
        "images": {"worker": {"image_repository": "vn-news-worker"}},
    }

    assert retag_command(catalog, "worker", "0.2.31", "0.2.32") == [
        "docker",
        "buildx",
        "imagetools",
        "create",
        "--tag",
        "docker.io/example/vn-news-worker:0.2.32",
        "docker.io/example/vn-news-worker:0.2.31",
    ]


def test_publish_images_rejects_copy_without_source_tag() -> None:
    with pytest.raises(ValueError, match="from_tag is required"):
        publish_images(
            tag="0.2.32",
            from_tag="",
            build_images=[],
            copy_images=["app_api"],
            push=True,
            github_actions_cache=False,
            dry_run=True,
        )
