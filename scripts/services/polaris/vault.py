from __future__ import annotations

import argparse
import base64
import os
import subprocess


def add_vault_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--runtime-credentials-secret-id",
        default=os.environ.get("VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID"),
    )
    parser.add_argument("--oci-bin", default=os.environ.get("OCI_BIN", "oci"))
    parser.add_argument(
        "--oci-auth",
        default=os.environ.get("VN_NEWS_OCI_AUTH", "instance_principal"),
    )


def require_secret_id(args: argparse.Namespace) -> str:
    if not args.runtime_credentials_secret_id:
        raise ValueError("VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID is required")
    return args.runtime_credentials_secret_id


def oci_command(args: argparse.Namespace, *parts: str) -> list[str]:
    command = [args.oci_bin, *parts]
    if args.oci_auth != "default":
        command.extend(["--auth", args.oci_auth])
    return command


def read_secret(args: argparse.Namespace, secret_id: str) -> str:
    result = subprocess.run(
        oci_command(
            args,
            "secrets",
            "secret-bundle",
            "get",
            "--secret-id",
            secret_id,
            "--query",
            'data."secret-bundle-content".content',
            "--raw-output",
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    return base64.b64decode(result.stdout.strip()).decode("utf-8")


def update_secret(
    args: argparse.Namespace,
    *,
    secret_id: str,
    content: str,
    content_name: str,
) -> None:
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    subprocess.run(
        oci_command(
            args,
            "vault",
            "secret",
            "update-base64",
            "--secret-id",
            secret_id,
            "--secret-content-content",
            encoded,
            "--secret-content-stage",
            "CURRENT",
            "--secret-content-name",
            content_name,
            "--force",
            "--wait-for-state",
            "ACTIVE",
        ),
        check=True,
        stdout=subprocess.DEVNULL,
    )
