from __future__ import annotations

import argparse
import json

import httpx
from news_platform.config import get_topic_name, load_settings
from news_platform.contracts.events import EVENT_TOPIC_KEYS, event_json_schema


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register event JSON Schemas in Redpanda.")
    parser.add_argument("--registry-url")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print subjects without registering.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_settings()
    registry_url = (args.registry_url or config["event_bus"]["schema_registry_url"]).rstrip("/")

    for topic_key, event_name in sorted(EVENT_TOPIC_KEYS.items()):
        topic = get_topic_name(config, topic_key)
        subject = f"{topic}-value"
        schema = event_json_schema(event_name)
        if args.dry_run:
            print(f"would register {subject} -> {event_name}")
            continue

        response = httpx.post(
            f"{registry_url}/subjects/{subject}/versions",
            json={"schemaType": "JSON", "schema": json.dumps(schema, sort_keys=True)},
            timeout=10,
        )
        response.raise_for_status()
        version = response.json().get("version", "unknown")
        print(f"registered {subject} version={version}")


if __name__ == "__main__":
    main()
