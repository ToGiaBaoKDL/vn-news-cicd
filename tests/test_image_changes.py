from __future__ import annotations

from scripts.images.changed import path_matches, selected_images


def test_path_matches_directory_glob() -> None:
    assert path_matches("services/article_fetcher/**", "services/article_fetcher/src/main.py")
    assert path_matches("services/article_fetcher/**", "services/article_fetcher")
    assert not path_matches("services/article_fetcher/**", "services/article_extractor/src/main.py")


def test_selected_images_returns_only_affected_service() -> None:
    catalog = {
        "change_paths": ["images.yaml", "services/common/**"],
        "images": {
            "article_fetcher": {"change_paths": ["services/article_fetcher/**"]},
            "article_extractor": {"change_paths": ["services/article_extractor/**"]},
        },
    }

    assert selected_images(catalog, ("services/article_fetcher/src/main.py",)) == (
        "article_fetcher",
    )


def test_selected_images_returns_all_for_shared_change() -> None:
    catalog = {
        "change_paths": ["images.yaml", "services/common/**"],
        "images": {
            "article_fetcher": {"change_paths": ["services/article_fetcher/**"]},
            "article_extractor": {"change_paths": ["services/article_extractor/**"]},
        },
    }

    assert selected_images(catalog, ("services/common/src/runtime.py",)) == (
        "article_extractor",
        "article_fetcher",
    )


def test_selected_images_can_build_all() -> None:
    catalog = {
        "change_paths": ["images.yaml"],
        "images": {
            "web": {"change_paths": ["web/**"]},
            "api": {"change_paths": ["api/**"]},
        },
    }

    assert selected_images(catalog, (), build_all=True) == ("api", "web")


def test_selected_images_ignores_workflow_only_change() -> None:
    catalog = {
        "change_paths": ["images.yaml"],
        "images": {
            "web": {"change_paths": ["web/**"]},
            "api": {"change_paths": ["api/**"]},
        },
    }

    assert selected_images(catalog, (".github/workflows/publish-images.yaml",)) == ()
