from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from scripts.services.polaris.cli import PolarisCli
from scripts.services.polaris.config import (
    add_bootstrap_credentials_argument,
    add_deploy_config_arguments,
    build_deploy_config,
    credentials_payload,
    env_bool,
    load_credentials,
    render_runtime_setup_config,
    runtime_credentials_are_pending,
    write_setup_config,
)
from scripts.services.polaris.vault import (
    add_vault_arguments,
    read_secret,
    require_secret_id,
    update_secret,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision Polaris runtime access.")
    add_deploy_config_arguments(parser)
    add_bootstrap_credentials_argument(parser)
    add_vault_arguments(parser)
    parser.add_argument(
        "--rotate-runtime-credentials",
        action="store_true",
        default=env_bool("VN_NEWS_POLARIS_ROTATE_RUNTIME_CREDENTIALS"),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def maybe_update_runtime_secret(
    args: argparse.Namespace,
    *,
    secret_id: str,
    credentials_content: str,
) -> None:
    if args.dry_run:
        print("would update Polaris runtime client credentials in OCI Vault")
        return
    update_secret(
        args,
        secret_id=secret_id,
        content=credentials_content,
        content_name=f"polaris-runtime-{datetime.now(UTC):%Y%m%dT%H%M%SZ}",
    )
    print("updated Polaris runtime client credentials in OCI Vault")


def provision(args: argparse.Namespace) -> None:
    config = build_deploy_config(args)
    bootstrap_credentials = load_credentials(
        args.credentials_file,
        "Polaris bootstrap credentials",
    )
    cli = PolarisCli(
        base_url=config.base_url,
        credentials=bootstrap_credentials,
    )
    secret_id = require_secret_id(args)
    current_credentials_content = "{}" if args.dry_run else read_secret(args, secret_id)
    pending_credentials = (
        False if args.dry_run else runtime_credentials_are_pending(current_credentials_content)
    )

    new_credentials = None
    if args.rotate_runtime_credentials or pending_credentials:
        if not args.dry_run:
            if not cli.resource_exists("principals", "get", config.runtime_principal_name):
                new_credentials = cli.create_runtime_principal(config)
            else:
                new_credentials = cli.rotate_runtime_credentials(config)
    elif not args.dry_run:
        new_credentials = cli.create_runtime_principal(config)

    with tempfile.TemporaryDirectory(prefix="vn-news-polaris-setup-") as tmp_dir:
        setup_path = Path(tmp_dir) / "setup.yaml"
        write_setup_config(setup_path, render_runtime_setup_config(config))
        cli.setup_apply(setup_path, dry_run=args.dry_run)

    if args.dry_run:
        print("would remove managed legacy Polaris catalog roles")
    else:
        cli.cleanup_legacy_catalog_roles(config)

    if new_credentials is not None:
        maybe_update_runtime_secret(
            args,
            secret_id=secret_id,
            credentials_content=json.dumps(
                credentials_payload(new_credentials),
                separators=(",", ":"),
            )
            + "\n",
        )


def main() -> None:
    provision(parse_args())


if __name__ == "__main__":
    main()
