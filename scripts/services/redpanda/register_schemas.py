from __future__ import annotations

import argparse
import json
import time

import httpx
from news_platform.config import get_topic_name, load_settings
from news_platform.contracts.events import EVENT_TOPIC_KEYS, event_json_schema

REQUEST_ATTEMPTS = 6
REQUEST_RETRY_STATUSES = {400, 408, 425, 429, 500, 502, 503, 504}
REQUEST_SLEEP_SECONDS = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register event JSON Schemas in Redpanda.")
    parser.add_argument("--registry-url")
    parser.add_argument("--compatibility", default="BACKWARD")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print subjects without registering.",
    )
    return parser.parse_args()


def set_compatibility(registry_url: str, compatibility: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"would set schema compatibility: {compatibility}")
        return

    request_registry("PUT", f"{registry_url}/config", {"compatibility": compatibility})
    print(f"schema compatibility set: {compatibility}")


def request_registry(method: str, url: str, payload: dict[str, object]) -> httpx.Response:
    response = httpx.Response(599, request=httpx.Request(method, url))
    for attempt in range(1, REQUEST_ATTEMPTS + 1):
        try:
            response = httpx.request(method, url, json=payload, timeout=10)
        except httpx.RequestError as error:
            if attempt == REQUEST_ATTEMPTS:
                raise
            print(
                f"schema registry {method} {url} failed with "
                f"{type(error).__name__}; retrying {attempt}/{REQUEST_ATTEMPTS}"
            )
            time.sleep(REQUEST_SLEEP_SECONDS)
            continue
        if response.status_code < 400:
            return response
        if response.status_code not in REQUEST_RETRY_STATUSES or attempt == REQUEST_ATTEMPTS:
            break
        print(
            f"schema registry {method} {url} returned {response.status_code}; "
            f"retrying {attempt}/{REQUEST_ATTEMPTS}"
        )
        time.sleep(REQUEST_SLEEP_SECONDS)

    raise_registry_status(response)
    return response


def raise_registry_status(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        body = response.text.strip()
        if body:
            error.add_note(f"schema registry response body: {body[:1000]}")
        raise


def main() -> None:
    args = parse_args()
    config = load_settings()
    registry_url = (args.registry_url or config["event_bus"]["schema_registry_url"]).rstrip("/")
    set_compatibility(registry_url, args.compatibility, dry_run=args.dry_run)

    for topic_key, event_name in sorted(EVENT_TOPIC_KEYS.items()):
        topic = get_topic_name(config, topic_key)
        subject = f"{topic}-value"
        schema = event_json_schema(event_name)
        if args.dry_run:
            print(f"would register {subject} -> {event_name}")
            continue

        response = request_registry(
            "POST",
            f"{registry_url}/subjects/{subject}/versions",
            {"schemaType": "JSON", "schema": json.dumps(schema, sort_keys=True)},
        )
        version = response.json().get("version", "unknown")
        print(f"registered {subject} version={version}")


if __name__ == "__main__":
    main()
