from __future__ import annotations

from datetime import datetime

import pytest
from news_platform.config import load_settings
from news_platform.contracts.tables import load_table_specs
from news_platform.ids import make_run_id, normalize_article_url
from news_platform.storage import StorageLayout


def test_bucket_suffixes_are_unique() -> None:
    config = load_settings()
    buckets = config["storage"]["buckets"]
    suffixes = [bucket.rsplit("-", maxsplit=1)[-1] for bucket in buckets.values()]
    assert len(suffixes) == len(set(suffixes))


def test_unknown_tgb_env_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("TGB_ENV", "staging")
    with pytest.raises(ValueError, match="Unknown environment: staging"):
        load_settings()


def test_warehouse_paths_use_configured_prefix() -> None:
    config = load_settings()
    layout = StorageLayout.from_config(config)
    for table in load_table_specs():
        uri = layout.warehouse_uri(table.bucket, table.name)
        assert uri.endswith(f"/{config['storage']['warehouse_prefix']}/{table.name}/")


def test_run_id_format() -> None:
    run_id = make_run_id("vnexpress", "kinh_doanh", datetime(2026, 5, 29, 8, 30, 5))
    assert run_id == "vnexpress_kinh_doanh_20260529T083005"


def test_article_url_normalization_removes_tracking_parameters() -> None:
    url = "HTTPS://VNEXPRESS.NET/a.html?utm_source=rss&id=1#top"

    assert normalize_article_url(url) == "https://vnexpress.net/a.html?id=1"
