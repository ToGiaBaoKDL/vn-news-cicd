from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from scripts.services.polaris.cli import PolarisCli
from scripts.services.polaris.config import (
    add_deploy_config_arguments,
    build_deploy_config,
    load_credentials,
)
from scripts.services.polaris.vault import add_vault_arguments, read_secret, require_secret_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Polaris runtime access.")
    add_deploy_config_arguments(parser)
    add_vault_arguments(parser)
    return parser.parse_args()


def validate(args: argparse.Namespace) -> None:
    config = build_deploy_config(args)
    secret_id = require_secret_id(args)
    with tempfile.TemporaryDirectory(prefix="vn-news-polaris-runtime-") as tmp_dir:
        credentials_file = Path(tmp_dir) / "polaris-client-credentials.json"
        credentials_file.write_text(read_secret(args, secret_id), encoding="utf-8")
        runtime_credentials = load_credentials(
            credentials_file,
            "Polaris runtime credentials",
        )
        cli = PolarisCli(base_url=config.base_url, credentials=runtime_credentials)
        for namespace in config.runtime_namespaces:
            cli.run(
                "tables",
                "list",
                "--catalog",
                config.catalog_name,
                "--namespace",
                namespace,
                capture_output=True,
            )
            print(f"validated Polaris runtime table listing: {config.catalog_name}.{namespace}")


def main() -> None:
    validate(parse_args())


if __name__ == "__main__":
    main()
