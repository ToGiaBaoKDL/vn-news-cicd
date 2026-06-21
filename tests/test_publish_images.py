from __future__ import annotations

import pytest
from scripts.images.publish import parse_csv, publish_images, retag_command


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


def test_publish_images_defaults_to_building_all_images(monkeypatch) -> None:
    commands = []
    catalog = {
        "registry": "docker.io",
        "namespace": "example",
        "images": {
            "api": {
                "image_repository": "vn-news-api",
                "build": {"context": ".", "dockerfile": "Dockerfile"},
            },
            "worker": {
                "image_repository": "vn-news-worker",
                "build": {"context": ".", "dockerfile": "Dockerfile"},
            },
        },
    }

    monkeypatch.setattr("scripts.images.publish.load_image_catalog", lambda: catalog)
    monkeypatch.setattr(
        "scripts.images.publish.image_command",
        lambda catalog, image_key, tag, push, github_actions_cache: ["build", image_key],
    )
    monkeypatch.setattr(
        "scripts.images.publish.run_command",
        lambda command, dry_run: commands.append(command),
    )

    publish_images(
        tag="0.2.32",
        from_tag="",
        build_images=[],
        copy_images=[],
        push=True,
        github_actions_cache=False,
        dry_run=True,
    )

    assert commands == [["build", "api"], ["build", "worker"]]
