from __future__ import annotations

import pytest
from scripts.images.manifest import parse_image_manifest, shell_exports


def digest_ref(repository: str) -> str:
    return f"docker.io/example/{repository}@sha256:{'a' * 64}"


def test_shell_exports_include_role_scoped_image_refs() -> None:
    catalog = {
        "registry": "docker.io",
        "namespace": "example",
        "owners": {"vn-news-app": {}, "vn-news-infra": {}},
        "images": {
            "api": {
                "owner": "vn-news-app",
                "image_repository": "vn-news-api",
                "image_env": "VN_NEWS_API_IMAGE",
                "roles": ["control"],
            },
            "runtime": {
                "owner": "vn-news-infra",
                "image_repository": "vn-news-runtime",
                "image_env": "VN_NEWS_RUNTIME_IMAGE",
                "roles": ["processing"],
            },
        },
    }
    image_refs = {
        "api": digest_ref("vn-news-api"),
        "runtime": digest_ref("vn-news-runtime"),
    }

    exports = shell_exports(catalog, image_refs, role="control")

    assert f"export VN_NEWS_API_IMAGE={digest_ref('vn-news-api')}" in exports
    assert "VN_NEWS_RUNTIME_IMAGE" not in exports
    assert "export VN_NEWS_IMAGE_MANIFEST=" in exports


def test_json_manifest_requires_string_values() -> None:
    catalog = {
        "registry": "docker.io",
        "namespace": "example",
        "owners": {"vn-news-app": {}},
        "images": {
            "api": {
                "owner": "vn-news-app",
                "image_repository": "vn-news-api",
                "image_env": "VN_NEWS_API_IMAGE",
                "roles": ["control"],
            }
        },
    }

    with pytest.raises(ValueError, match="image keys and refs must be strings"):
        parse_image_manifest('{"vn-news-app": null}', catalog)


def test_manifest_requires_digest_pinned_refs() -> None:
    catalog = {
        "registry": "docker.io",
        "namespace": "example",
        "owners": {"vn-news-app": {}},
        "images": {
            "api": {
                "owner": "vn-news-app",
                "image_repository": "vn-news-api",
                "image_env": "VN_NEWS_API_IMAGE",
                "roles": ["control"],
            }
        },
    }

    with pytest.raises(ValueError, match="digest-pinned"):
        parse_image_manifest('{"api":"docker.io/example/vn-news-api:sha-app"}', catalog)
