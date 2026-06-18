from __future__ import annotations

from pathlib import Path

import pytest
from scripts.release_plan import (
    create_release_plan,
    image_dependency_map,
    previous_manifest_path,
)

REPOSITORIES = {
    "vn-news-cicd": "0" * 40,
    "vn-news-app": "1" * 40,
    "vn-news-config": "2" * 40,
    "vn-news-infra": "3" * 40,
    "vn-news-orchestration": "4" * 40,
    "vn-news-platform-lib": "5" * 40,
    "vn-news-services": "6" * 40,
}


CATALOG = {
    "images": {
        "app_api": {
            "build": {
                "repo": "vn-news-app",
                "additional_contexts": {"vn-news-platform-lib": "vn-news-platform-lib"},
            }
        },
        "app_web": {"build": {"repo": "vn-news-app"}},
        "infra_airflow_runtime": {"build": {"repo": "vn-news-infra"}},
        "service_article_fetcher": {
            "build": {
                "repo": "vn-news-services",
                "additional_contexts": {"vn-news-platform-lib": "vn-news-platform-lib"},
            }
        },
        "service_feed_ingestor": {
            "build": {
                "repo": "vn-news-services",
                "additional_contexts": {"vn-news-platform-lib": "vn-news-platform-lib"},
            }
        },
    }
}


def write_manifest(
    root: Path,
    filename: str,
    *,
    release_tag: str,
    image_tag: str,
    overrides: dict[str, str] | None = None,
) -> Path:
    repositories = {**REPOSITORIES, **(overrides or {})}
    lines = [
        "version = 1",
        f'release_tag = "{release_tag}"',
        f'image_tag = "{image_tag}"',
        "",
        "[repositories]",
    ]
    lines.extend(f'{repo} = "{commit}"' for repo, commit in repositories.items())
    path = root / filename
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_image_dependency_map_includes_additional_context_repos() -> None:
    dependencies = image_dependency_map(CATALOG)

    assert dependencies["app_api"] == {"vn-news-app", "vn-news-platform-lib"}
    assert dependencies["service_article_fetcher"] == {
        "vn-news-platform-lib",
        "vn-news-services",
    }


def test_release_plan_builds_only_service_images_for_service_change(tmp_path: Path) -> None:
    base = write_manifest(
        tmp_path,
        "0.2.30.toml",
        release_tag="0.2.30",
        image_tag="0.2.30",
    )
    current = write_manifest(
        tmp_path,
        "0.2.31.toml",
        release_tag="0.2.31",
        image_tag="0.2.31",
        overrides={"vn-news-services": "7" * 40},
    )

    plan = create_release_plan(
        current_manifest_path=current,
        base_manifest_path=base,
        catalog=CATALOG,
    )

    assert plan.changed_repositories == ["vn-news-services"]
    assert plan.build_images == ["service_article_fetcher", "service_feed_ingestor"]
    assert plan.copy_images == ["app_api", "app_web", "infra_airflow_runtime"]
    assert plan.publish_required is True
    assert plan.deploy_data is False
    assert plan.deploy_control is False
    assert plan.deploy_processing is True


def test_release_plan_copies_images_for_config_only_release(tmp_path: Path) -> None:
    base = write_manifest(
        tmp_path,
        "0.2.31.toml",
        release_tag="0.2.31",
        image_tag="0.2.31",
    )
    current = write_manifest(
        tmp_path,
        "0.2.32.toml",
        release_tag="0.2.32",
        image_tag="0.2.32",
        overrides={"vn-news-config": "8" * 40},
    )

    plan = create_release_plan(
        current_manifest_path=current,
        base_manifest_path=base,
        catalog=CATALOG,
    )

    assert plan.build_images == []
    assert plan.copy_images == sorted(CATALOG["images"])
    assert plan.publish_required is True
    assert plan.deploy_data is True
    assert plan.deploy_control is True
    assert plan.deploy_processing is True


def test_release_plan_does_not_rebuild_images_for_cicd_only_release(
    tmp_path: Path,
) -> None:
    base = write_manifest(
        tmp_path,
        "0.2.31.toml",
        release_tag="0.2.31",
        image_tag="0.2.31",
    )
    current = write_manifest(
        tmp_path,
        "0.2.32.toml",
        release_tag="0.2.32",
        image_tag="0.2.32",
        overrides={"vn-news-cicd": "8" * 40},
    )

    plan = create_release_plan(
        current_manifest_path=current,
        base_manifest_path=base,
        catalog=CATALOG,
    )

    assert plan.changed_repositories == ["vn-news-cicd"]
    assert plan.build_images == []
    assert plan.copy_images == sorted(CATALOG["images"])
    assert plan.publish_required is True
    assert plan.deploy_data is True
    assert plan.deploy_control is True
    assert plan.deploy_processing is True


def test_release_plan_ignores_cicd_manifest_only_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "scripts.release_plan.repository_has_functional_changes",
        lambda repo_name, base_ref, commit_ref: False,
    )
    base = write_manifest(
        tmp_path,
        "0.2.31.toml",
        release_tag="0.2.31",
        image_tag="0.2.31",
    )
    current = write_manifest(
        tmp_path,
        "0.2.32.toml",
        release_tag="0.2.32",
        image_tag="0.2.32",
        overrides={"vn-news-cicd": "8" * 40},
    )

    plan = create_release_plan(
        current_manifest_path=current,
        base_manifest_path=base,
        catalog=CATALOG,
    )

    assert plan.changed_repositories == []
    assert plan.build_images == []
    assert plan.copy_images == []
    assert plan.publish_required is False
    assert plan.deploy_data is False
    assert plan.deploy_control is False
    assert plan.deploy_processing is False


def test_release_plan_rejects_reused_image_tag_for_image_change(tmp_path: Path) -> None:
    base = write_manifest(
        tmp_path,
        "0.2.31.toml",
        release_tag="0.2.31",
        image_tag="0.2.31",
    )
    current = write_manifest(
        tmp_path,
        "0.2.32.toml",
        release_tag="0.2.32",
        image_tag="0.2.31",
        overrides={"vn-news-services": "9" * 40},
    )

    with pytest.raises(ValueError, match="image_tag did not change"):
        create_release_plan(
            current_manifest_path=current,
            base_manifest_path=base,
            catalog=CATALOG,
        )


def test_previous_manifest_uses_semantic_version_order(tmp_path: Path) -> None:
    write_manifest(tmp_path, "0.2.9.toml", release_tag="0.2.9", image_tag="0.2.9")
    previous = write_manifest(
        tmp_path,
        "0.2.31.toml",
        release_tag="0.2.31",
        image_tag="0.2.31",
    )
    current = write_manifest(
        tmp_path,
        "0.2.32.toml",
        release_tag="0.2.32",
        image_tag="0.2.32",
    )

    assert previous_manifest_path(current) == previous
