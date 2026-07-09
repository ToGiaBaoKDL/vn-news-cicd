from __future__ import annotations

import httpx
import pytest
from scripts.services.redpanda import provision_topics, register_schemas


def test_provision_topics_disables_auto_create_and_reconciles_retention(monkeypatch) -> None:
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

    monkeypatch.setattr(provision_topics, "load_settings", lambda: config)
    monkeypatch.setattr(
        provision_topics,
        "parse_args",
        lambda: provision_topics.argparse.Namespace(
            brokers=None,
            rpk_command="rpk",
            disable_enterprise_balancing=True,
            disable_auto_create=True,
            dry_run=False,
        ),
    )
    monkeypatch.setattr(
        provision_topics.subprocess,
        "run",
        lambda command, check: commands.append(command),
    )

    provision_topics.main()

    assert commands[0] == [
        "rpk",
        "cluster",
        "config",
        "set",
        "core_balancing_continuous",
        "false",
        "--no-confirm",
        "-X",
        "brokers=redpanda:9092",
    ]
    assert commands[1] == [
        "rpk",
        "cluster",
        "config",
        "set",
        "partition_autobalancing_mode",
        "off",
        "--no-confirm",
        "-X",
        "brokers=redpanda:9092",
    ]
    assert commands[2] == [
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
    assert commands[3] == [
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
    assert commands[4] == [
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


def test_register_schemas_registers_topic_subjects(monkeypatch) -> None:
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
        def __init__(
            self, payload: dict[str, object] | None = None, status_code: int = 200
        ) -> None:
            self.payload = payload or {}
            self.status_code = status_code

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
            dry_run=False,
        ),
    )

    def request(method, url, json, timeout):
        calls.append((method, url, json))
        if method == "POST":
            return Response({"version": 1})
        return Response()

    monkeypatch.setattr(register_schemas.httpx, "request", request)

    register_schemas.main()

    assert calls[0][0] == "POST"
    assert (
        calls[0][1] == "http://redpanda:8081/subjects/vn.news.feed_item.discovered-value/versions"
    )


def test_register_schemas_surfaces_registry_errors(monkeypatch) -> None:
    config = {
        "event_bus": {
            "topics": {
                "feed_item_discovered": {
                    "name": "vn.news.feed_item.discovered",
                }
            },
        }
    }
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
            registry_url="http://redpanda:8081",
            dry_run=False,
        ),
    )

    monkeypatch.setattr(register_schemas, "REQUEST_ATTEMPTS", 1)

    def fail_request(method, url, json, timeout):
        response = httpx.Response(500, request=httpx.Request(method, url), text="not ready")
        return response

    monkeypatch.setattr(register_schemas.httpx, "request", fail_request)

    with pytest.raises(httpx.HTTPStatusError):
        register_schemas.main()
