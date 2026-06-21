from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
import yaml
from news_platform.config import load_settings
from news_platform.ids import make_run_id, normalize_article_url
from scripts.workspace.verify import (
    validate_release_identity_usage,
    validate_workflow_action_ref,
)


def test_bucket_suffixes_are_unique() -> None:
    config = load_settings()
    buckets = config["storage"]["buckets"]
    suffixes = [bucket.rsplit("-", maxsplit=1)[-1] for bucket in buckets.values()]
    assert len(suffixes) == len(set(suffixes))


def test_deployment_endpoint_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("VN_NEWS_STORAGE_ENDPOINT_URL", "http://10.0.0.10:8333")
    monkeypatch.setenv("VN_NEWS_REDPANDA_BOOTSTRAP_SERVERS", "10.0.0.10:19092")
    monkeypatch.setenv("VN_NEWS_SCHEMA_REGISTRY_URL", "http://10.0.0.10:18081")

    config = load_settings()

    assert config["storage"]["endpoint_url"] == "http://10.0.0.10:8333"
    assert config["event_bus"]["bootstrap_servers"] == "10.0.0.10:19092"
    assert config["event_bus"]["schema_registry_url"] == "http://10.0.0.10:18081"


def test_run_id_format() -> None:
    run_id = make_run_id("vnexpress", "kinh_doanh", datetime(2026, 5, 29, 8, 30, 5))
    assert run_id == "vnexpress_kinh_doanh_20260529T083005"


def test_article_url_normalization_removes_tracking_parameters() -> None:
    url = "HTTPS://VNEXPRESS.NET/a.html?utm_source=rss&id=1#top"

    assert normalize_article_url(url) == "https://vnexpress.net/a.html?id=1"


def test_workflow_action_ref_accepts_commit_sha() -> None:
    validate_workflow_action_ref(
        path=Path("workflow.yaml"),
        action="actions/checkout",
        ref="df4cb1c069e1874edd31b4311f1884172cec0e10",
    )


def test_workflow_action_ref_rejects_tag() -> None:
    with pytest.raises(ValueError, match="immutable commit SHA"):
        validate_workflow_action_ref(
            path=Path("workflow.yaml"), action="actions/checkout", ref="v6"
        )


def test_processing_deploy_waits_for_data_and_spark_master() -> None:
    workflow = yaml.safe_load(
        Path(".github/workflows/release-production.yaml").read_text(encoding="utf-8")
    )

    assert set(workflow["jobs"]["deploy-processing"]["needs"]) == {
        "plan",
        "verify-images",
        "deploy-data",
        "deploy-control",
    }
    condition = workflow["jobs"]["deploy-processing"]["if"]
    assert "needs['deploy-control'].result == 'success'" in condition
    assert "needs['deploy-control'].result == 'skipped'" in condition


def test_deploy_uses_distinct_release_and_image_tags() -> None:
    workflow = yaml.safe_load(
        Path(".github/workflows/release-production.yaml").read_text(encoding="utf-8")
    )

    for job_name in ("deploy-data", "deploy-control", "deploy-processing"):
        deploy_step = next(
            step
            for step in workflow["jobs"][job_name]["steps"]
            if step["name"].startswith("Deploy ")
        )
        assert deploy_step["env"]["RELEASE_TAG"] == "${{ needs.plan.outputs.release_tag }}"
        assert deploy_step["env"]["IMAGE_TAG"] == "${{ needs.plan.outputs.image_tag }}"

    validate_release_identity_usage()


def test_release_workflow_enables_github_actions_build_cache() -> None:
    workflow = Path(".github/workflows/release-production.yaml").read_text(encoding="utf-8")

    assert "publish_required" in workflow
    assert "--github-actions-cache" in workflow
    assert "crazy-max/ghaction-github-runtime@" in workflow
    assert "python -m scripts.images.publish" in workflow
    assert "python -m scripts.images.build --tag" not in workflow
