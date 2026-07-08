from __future__ import annotations

import pytest
from scripts.images.manifest import parse_image_manifest, shell_exports


def test_shell_exports_include_registry_namespace_and_owner_tags() -> None:
    catalog = {
        "registry": "docker.io",
        "namespace": "example",
        "owners": {
            "vn-news-app": {"tag_env": "VN_NEWS_APP_IMAGE_TAG"},
            "vn-news-infra": {"tag_env": "VN_NEWS_INFRA_IMAGE_TAG"},
        },
        "images": {
            "api": {"owner": "vn-news-app", "image_repository": "vn-news-api"},
            "runtime": {"owner": "vn-news-infra", "image_repository": "vn-news-runtime"},
        },
    }

    exports = shell_exports(
        catalog,
        {"vn-news-app": "sha-app", "vn-news-infra": "sha-infra"},
    )

    assert "export VN_NEWS_IMAGE_REGISTRY=docker.io" in exports
    assert "export VN_NEWS_IMAGE_NAMESPACE=example" in exports
    assert "export VN_NEWS_APP_IMAGE_TAG=sha-app" in exports
    assert "export VN_NEWS_INFRA_IMAGE_TAG=sha-infra" in exports


def test_json_manifest_requires_string_values() -> None:
    catalog = {
        "owners": {"vn-news-app": {"tag_env": "VN_NEWS_APP_IMAGE_TAG"}},
        "images": {"api": {"owner": "vn-news-app", "image_repository": "vn-news-api"}},
    }

    with pytest.raises(ValueError, match="owners and tags must be strings"):
        parse_image_manifest('{"vn-news-app": null}', catalog)
