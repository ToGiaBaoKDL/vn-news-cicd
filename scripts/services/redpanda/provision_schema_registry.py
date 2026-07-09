from __future__ import annotations

import argparse
import time

from news_platform.config import load_settings

from scripts.services.redpanda import rpk

SCHEMA_REGISTRY_TOPIC = "_schemas"
SCHEMA_REGISTRY_TOPIC_CONFIG = {
    "cleanup.policy": "compact",
    "retention.ms": "-1",
    "retention.bytes": "-1",
}
DELETE_WAIT_ATTEMPTS = 30
DELETE_WAIT_SECONDS = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision Redpanda Schema Registry metadata.")
    parser.add_argument("--brokers")
    parser.add_argument("--rpk-command", default="rpk")
    parser.add_argument(
        "--recreate-schema-topic",
        action="store_true",
        help="Delete and recreate _schemas. Use only when registry metadata is corrupted.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def topic_exists(prefix: list[str], brokers: str, topic: str) -> bool:
    output = rpk.capture(
        rpk.command(prefix, "topic", "list", brokers=brokers),
    )
    return any(line.split(maxsplit=1)[0] == topic for line in output.splitlines() if line.strip())


def wait_topic_absent(prefix: list[str], brokers: str, topic: str) -> None:
    for _ in range(DELETE_WAIT_ATTEMPTS):
        if not topic_exists(prefix, brokers, topic):
            return
        time.sleep(DELETE_WAIT_SECONDS)
    raise TimeoutError(f"Timed out waiting for Redpanda topic to be deleted: {topic}")


def config_args(flag: str) -> list[str]:
    args: list[str] = []
    for key, value in SCHEMA_REGISTRY_TOPIC_CONFIG.items():
        args.extend([flag, f"{key}={value}"])
    return args


def recreate_topic(prefix: list[str], brokers: str, *, dry_run: bool) -> None:
    if dry_run:
        rpk.run(
            rpk.command(prefix, "topic", "delete", SCHEMA_REGISTRY_TOPIC, brokers=brokers),
            dry_run=True,
        )
        return

    if not topic_exists(prefix, brokers, SCHEMA_REGISTRY_TOPIC):
        return
    rpk.run(
        rpk.command(prefix, "topic", "delete", SCHEMA_REGISTRY_TOPIC, brokers=brokers),
        dry_run=False,
    )
    wait_topic_absent(prefix, brokers, SCHEMA_REGISTRY_TOPIC)


def provision_topic(prefix: list[str], brokers: str, *, dry_run: bool) -> None:
    rpk.run(
        rpk.command(
            prefix,
            "topic",
            "create",
            SCHEMA_REGISTRY_TOPIC,
            "--if-not-exists",
            "--partitions",
            "1",
            *config_args("--topic-config"),
            brokers=brokers,
        ),
        dry_run=dry_run,
    )
    rpk.run(
        rpk.command(
            prefix,
            "topic",
            "alter-config",
            SCHEMA_REGISTRY_TOPIC,
            *config_args("--set"),
            "--no-confirm",
            brokers=brokers,
        ),
        dry_run=dry_run,
    )


def main() -> None:
    args = parse_args()
    config = load_settings()
    prefix = rpk.split_prefix(args.rpk_command)
    brokers = args.brokers or config["event_bus"]["bootstrap_servers"]

    if args.recreate_schema_topic:
        recreate_topic(prefix, brokers, dry_run=args.dry_run)
    provision_topic(prefix, brokers, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
