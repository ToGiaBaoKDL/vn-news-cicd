from __future__ import annotations

import pytest
from scripts.images.build import image_command, validate_tag


@pytest.mark.parametrize("tag", ["0.1.0", "2026-06-02.1", "sha-a1b2c3d"])
def test_validate_tag_accepts_immutable_tags(tag: str) -> None:
    validate_tag(tag, push=True)


def test_validate_tag_rejects_latest_for_publish() -> None:
    with pytest.raises(ValueError, match="immutable image tag"):
        validate_tag("latest", push=True)


def test_validate_tag_allows_latest_for_local_build() -> None:
    validate_tag("latest", push=False)


def test_validate_tag_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="Invalid Docker image tag"):
        validate_tag("../escape", push=False)


def test_pushed_image_uses_catalog_platforms() -> None:
    catalog = {
        "registry": "docker.io",
        "namespace": "example",
        "platforms": ["linux/amd64", "linux/arm64"],
        "images": {
            "airflow_runtime": {
                "image_repository": "vn-news-airflow-runtime",
                "build": {
                    "context": "vn-news-infra/airflow/runtime",
                    "dockerfile": "Dockerfile",
                },
            },
        },
    }

    command = image_command(catalog, "airflow_runtime", "0.2.5", push=True)

    assert "--platform" in command
    assert "linux/amd64,linux/arm64" in command
    assert "--push" in command


def test_local_image_load_does_not_use_multi_platforms() -> None:
    catalog = {
        "registry": "docker.io",
        "namespace": "example",
        "platforms": ["linux/amd64", "linux/arm64"],
        "images": {
            "airflow_runtime": {
                "image_repository": "vn-news-airflow-runtime",
                "build": {
                    "context": "vn-news-infra/airflow/runtime",
                    "dockerfile": "Dockerfile",
                },
            },
        },
    }

    command = image_command(catalog, "airflow_runtime", "local", push=False)

    assert "--platform" not in command
    assert "--load" in command
