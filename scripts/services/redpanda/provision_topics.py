from __future__ import annotations

import argparse

from news_platform.config import load_settings

from scripts.services.redpanda import rpk

REDPANDA_COMMUNITY_CONFIG = {
    "core_balancing_continuous": "false",
    "partition_autobalancing_mode": "off",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision application Redpanda topics.")
    parser.add_argument("--brokers")
    parser.add_argument("--rpk-command", default="rpk")
    parser.add_argument("--disable-enterprise-balancing", action="store_true")
    parser.add_argument("--disable-auto-create", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_settings()
    prefix = rpk.split_prefix(args.rpk_command)
    brokers = args.brokers or config["event_bus"]["bootstrap_servers"]
    if args.disable_enterprise_balancing:
        for key, value in REDPANDA_COMMUNITY_CONFIG.items():
            rpk.run(
                rpk.command(
                    prefix,
                    "cluster",
                    "config",
                    "set",
                    key,
                    value,
                    "--no-confirm",
                    brokers=brokers,
                ),
                dry_run=args.dry_run,
            )

    if args.disable_auto_create:
        rpk.run(
            rpk.command(
                prefix,
                "cluster",
                "config",
                "set",
                "auto_create_topics_enabled",
                "false",
                "--no-confirm",
                brokers=brokers,
            ),
            dry_run=args.dry_run,
        )

    for topic in config["event_bus"]["topics"].values():
        topic_name = topic["name"]
        retention_ms = topic["retention_ms"]
        retention_bytes = topic["retention_bytes"]
        rpk.run(
            rpk.command(
                prefix,
                "topic",
                "create",
                topic_name,
                "--if-not-exists",
                "--partitions",
                str(topic["partitions"]),
                "--topic-config",
                f"retention.ms={retention_ms}",
                "--topic-config",
                f"retention.bytes={retention_bytes}",
                brokers=brokers,
            ),
            dry_run=args.dry_run,
        )
        rpk.run(
            rpk.command(
                prefix,
                "topic",
                "alter-config",
                topic_name,
                "--set",
                f"retention.ms={retention_ms}",
                "--set",
                f"retention.bytes={retention_bytes}",
                "--no-confirm",
                brokers=brokers,
            ),
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
