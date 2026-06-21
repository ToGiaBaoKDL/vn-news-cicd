from __future__ import annotations

import httpx
import pytest
from scripts.services.redpanda import bootstrap_topics, register_schemas


def test_bootstrap_topics_disables_auto_create_and_reconciles_retention(monkeypatch) -> None:
    config = {
        "event_bus": {
            "bootstrap_servers": "redpanda:9092",
            "topics": {
                "feed_item_discovered": {
                    "name": "vn.news.feed_item.discovered",
                    "partitions": 3,
                    "retention_ms": 604800000,
                    "retention_bytes": 268435456,
                }
            },
        }
    }
    commands: list[list[str]] = []

    monkeypatch.setattr(bootstrap_topics, "load_settings", lambda: config)
    monkeypatch.setattr(
        bootstrap_topics,
        "parse_args",
        lambda: bootstrap_topics.argparse.Namespace(
            brokers=None,
            rpk_command="rpk",
            disable_auto_create=True,
            dry_run=False,
        ),
    )
    monkeypatch.setattr(
        bootstrap_topics.subprocess,
        "run",
        lambda command, check: commands.append(command),
    )

    bootstrap_topics.main()

    assert commands[0] == [
        "rpk",
        "cluster",
        "config",
        "set",
        "auto_create_topics_enabled",
        "false",
        "--no-confirm",
        "-X",
        "brokers=redpanda:9092",
    ]
    assert commands[1] == [
        "rpk",
        "topic",
        "create",
        "vn.news.feed_item.discovered",
        "--if-not-exists",
        "--partitions",
        "3",
        "--topic-config",
        "retention.ms=604800000",
        "--topic-config",
        "retention.bytes=268435456",
        "-X",
        "brokers=redpanda:9092",
    ]
    assert commands[2] == [
        "rpk",
        "topic",
        "alter-config",
        "vn.news.feed_item.discovered",
        "--set",
        "retention.ms=604800000",
        "--set",
        "retention.bytes=268435456",
        "--no-confirm",
        "-X",
        "brokers=redpanda:9092",
    ]


def test_register_schemas_sets_compatibility_first(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []
    config = {
        "event_bus": {
            "schema_registry_url": "http://redpanda:8081",
            "topics": {
                "feed_item_discovered": {
                    "name": "vn.news.feed_item.discovered",
                }
            },
        }
    }

    class Response:
        def __init__(self, payload: dict[str, object] | None = None) -> None:
            self.payload = payload or {}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self.payload

    monkeypatch.setattr(register_schemas, "load_settings", lambda: config)
    monkeypatch.setattr(
        register_schemas,
        "EVENT_TOPIC_KEYS",
        {"feed_item_discovered": "feed_item_discovered"},
    )
    monkeypatch.setattr(
        register_schemas,
        "event_json_schema",
        lambda event_name: {"title": event_name},
    )
    monkeypatch.setattr(
        register_schemas,
        "parse_args",
        lambda: register_schemas.argparse.Namespace(
            registry_url=None,
            compatibility="BACKWARD",
            dry_run=False,
        ),
    )
    monkeypatch.setattr(
        register_schemas.httpx,
        "put",
        lambda url, json, timeout: calls.append(("PUT", url, json)) or Response(),
    )
    monkeypatch.setattr(
        register_schemas.httpx,
        "post",
        lambda url, json, timeout: calls.append(("POST", url, json)) or Response({"version": 1}),
    )

    register_schemas.main()

    assert calls[0] == (
        "PUT",
        "http://redpanda:8081/config",
        {"compatibility": "BACKWARD"},
    )
    assert calls[1][0] == "POST"
    assert (
        calls[1][1] == "http://redpanda:8081/subjects/vn.news.feed_item.discovered-value/versions"
    )


def test_register_schemas_surfaces_registry_errors(monkeypatch) -> None:
    monkeypatch.setattr(register_schemas, "load_settings", lambda: {"event_bus": {}})
    monkeypatch.setattr(
        register_schemas,
        "parse_args",
        lambda: register_schemas.argparse.Namespace(
            registry_url="http://redpanda:8081",
            compatibility="BACKWARD",
            dry_run=False,
        ),
    )

    def fail_put(url, json, timeout):
        response = httpx.Response(500, request=httpx.Request("PUT", url))
        return response

    monkeypatch.setattr(register_schemas.httpx, "put", fail_put)

    with pytest.raises(httpx.HTTPStatusError):
        register_schemas.main()
