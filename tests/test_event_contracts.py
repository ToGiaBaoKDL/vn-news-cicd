from __future__ import annotations

from news_platform.config import get_topic_name, load_settings
from news_platform.contracts.events import EVENT_CONTRACTS, EVENT_TOPIC_KEYS, event_json_schema


def test_event_contracts_cover_configured_topics() -> None:
    config = load_settings()
    assert set(config["event_bus"]["topics"]) == set(EVENT_TOPIC_KEYS)
    assert set(EVENT_CONTRACTS) == set(EVENT_TOPIC_KEYS.values())


def test_topic_definitions_are_provision_ready() -> None:
    config = load_settings()
    topics = config["event_bus"]["topics"]

    assert len({get_topic_name(config, topic_key) for topic_key in topics}) == len(topics)
    assert all(topic["partitions"] > 0 for topic in topics.values())
    assert all(topic["retention_ms"] > 0 for topic in topics.values())


def test_event_schemas_generate_from_models() -> None:
    for event_name in EVENT_CONTRACTS:
        schema = event_json_schema(event_name)
        assert schema["title"] == event_name
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
