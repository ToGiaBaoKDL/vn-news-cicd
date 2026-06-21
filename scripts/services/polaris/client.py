from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from news_platform.config import (
    get_lakehouse_catalog_name,
    get_lakehouse_warehouse_uri,
    load_settings,
)

DEFAULT_OAUTH_SCOPE = "PRINCIPAL_ROLE:ALL"
DEFAULT_STORAGE_REGION = "us-east-1"
PENDING_RUNTIME_CREDENTIALS_STATUS = "pending-polaris-runtime-principal"
UNIT_SEPARATOR = "\x1f"


@dataclass(frozen=True)
class PolarisCredentials:
    realm: str
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class PolarisCatalogConfig:
    management_url: str
    catalog_url: str
    catalog_name: str
    warehouse_uri: str
    storage_endpoint_url: str
    storage_endpoint_internal_url: str | None
    storage_sts_endpoint_url: str | None
    storage_role_arn: str | None
    storage_user_arn: str | None
    storage_external_id: str | None
    storage_region: str
    oauth_scope: str
    timeout_seconds: float


class PolarisClient:
    def __init__(
        self,
        client: httpx.Client,
        config: PolarisCatalogConfig,
        credentials: PolarisCredentials,
    ) -> None:
        self.client = client
        self.config = config
        self.credentials = credentials
        self._access_token: str | None = None

    @property
    def token_url(self) -> str:
        return join_url(self.config.catalog_url, "v1", "oauth", "tokens")

    def auth_headers_for(
        self,
        credentials: PolarisCredentials,
        access_token: str,
    ) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Polaris-Realm": credentials.realm,
        }

    def auth_headers(self) -> dict[str, str]:
        if not self._access_token:
            raise RuntimeError("Polaris access token has not been requested")
        return self.auth_headers_for(self.credentials, self._access_token)

    def request_access_token(self, credentials: PolarisCredentials) -> str:
        response = self.client.post(
            self.token_url,
            data={"grant_type": "client_credentials", "scope": self.config.oauth_scope},
            auth=(credentials.client_id, credentials.client_secret),
            headers={"Polaris-Realm": credentials.realm},
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("Polaris token response did not include an access_token")
        return token

    def authenticate(self) -> None:
        self._access_token = self.request_access_token(self.credentials)


def default_secrets_dir() -> Path:
    return Path(os.environ.get("VN_NEWS_SECRETS_HOST_DIR", "/run/vn-news/secrets"))


def add_catalog_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--catalog-url", default=os.environ.get("VN_NEWS_POLARIS_CATALOG_URL"))
    parser.add_argument("--management-url")
    parser.add_argument("--catalog-name")
    parser.add_argument(
        "--storage-endpoint-url",
        default=os.environ.get("VN_NEWS_STORAGE_ENDPOINT_URL"),
    )
    parser.add_argument(
        "--storage-endpoint-internal-url",
        default=os.environ.get("VN_NEWS_POLARIS_STORAGE_ENDPOINT_INTERNAL_URL"),
    )
    parser.add_argument(
        "--storage-sts-endpoint-url",
        default=os.environ.get("VN_NEWS_POLARIS_STORAGE_STS_ENDPOINT_URL"),
    )
    parser.add_argument(
        "--storage-role-arn",
        default=os.environ.get("VN_NEWS_POLARIS_STORAGE_ROLE_ARN"),
    )
    parser.add_argument(
        "--storage-user-arn",
        default=os.environ.get("VN_NEWS_POLARIS_STORAGE_USER_ARN"),
    )
    parser.add_argument(
        "--storage-external-id",
        default=os.environ.get("VN_NEWS_POLARIS_STORAGE_EXTERNAL_ID"),
    )
    parser.add_argument(
        "--storage-region",
        default=os.environ.get("VN_NEWS_POLARIS_STORAGE_REGION", DEFAULT_STORAGE_REGION),
    )
    parser.add_argument("--warehouse-uri")
    parser.add_argument(
        "--oauth-scope",
        default=os.environ.get("VN_NEWS_POLARIS_OAUTH_SCOPE", DEFAULT_OAUTH_SCOPE),
    )
    parser.add_argument("--timeout-seconds", type=float, default=30.0)


def add_bootstrap_credentials_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--credentials-file",
        type=Path,
        default=default_secrets_dir() / "polaris-bootstrap-credentials.json",
    )


def derive_management_url(catalog_url: str) -> str:
    normalized = catalog_url.rstrip("/")
    suffix = "/api/catalog"
    if not normalized.endswith(suffix):
        raise ValueError(
            "Polaris management URL is required when catalog URL does not end with /api/catalog"
        )
    return f"{normalized[: -len(suffix)]}/api/management/v1"


def normalize_url(url: str | None, name: str) -> str:
    if not url or not url.strip():
        raise ValueError(f"{name} is required")
    return url.rstrip("/")


def derive_warehouse_uri(settings: dict[str, Any], explicit_uri: str | None) -> str:
    if explicit_uri:
        normalized_uri = explicit_uri.rstrip("/")
        if not normalized_uri:
            raise ValueError("warehouse URI must not be empty")
        return normalized_uri
    return get_lakehouse_warehouse_uri(settings)


def build_catalog_config(args: argparse.Namespace) -> PolarisCatalogConfig:
    settings = load_settings()
    catalog_url = normalize_url(args.catalog_url, "Polaris catalog URL")
    management_url = (
        normalize_url(args.management_url, "Polaris management URL") if args.management_url else ""
    )
    if not management_url:
        management_url = derive_management_url(catalog_url)

    storage_endpoint_url = args.storage_endpoint_url or settings["storage"]["endpoint_url"]
    catalog_name = args.catalog_name or get_lakehouse_catalog_name(settings)
    if not isinstance(catalog_name, str) or not catalog_name:
        raise ValueError("lakehouse.catalog_name must be a non-empty string")
    return PolarisCatalogConfig(
        management_url=management_url,
        catalog_url=catalog_url,
        catalog_name=catalog_name,
        warehouse_uri=derive_warehouse_uri(settings, args.warehouse_uri),
        storage_endpoint_url=normalize_url(storage_endpoint_url, "storage endpoint URL"),
        storage_endpoint_internal_url=(
            normalize_url(args.storage_endpoint_internal_url, "internal storage endpoint URL")
            if args.storage_endpoint_internal_url
            else None
        ),
        storage_sts_endpoint_url=(
            normalize_url(args.storage_sts_endpoint_url, "storage STS endpoint URL")
            if args.storage_sts_endpoint_url
            else None
        ),
        storage_role_arn=args.storage_role_arn or None,
        storage_user_arn=args.storage_user_arn or None,
        storage_external_id=args.storage_external_id or None,
        storage_region=args.storage_region,
        oauth_scope=args.oauth_scope,
        timeout_seconds=args.timeout_seconds,
    )


def parse_credentials_payload(payload: dict[str, Any], label: str) -> PolarisCredentials:
    if len(payload) != 1:
        raise ValueError(f"{label} must contain exactly one realm")

    realm, credentials = next(iter(payload.items()))
    if not isinstance(credentials, dict):
        raise ValueError(f"{label} for realm {realm} must be an object")

    client_id = credentials.get("client-id")
    client_secret = credentials.get("client-secret")
    if not isinstance(client_id, str) or not client_id:
        raise ValueError(f"{label} for realm {realm} missing client-id")
    if not isinstance(client_secret, str) or not client_secret:
        raise ValueError(f"{label} for realm {realm} missing client-secret")
    return PolarisCredentials(realm=realm, client_id=client_id, client_secret=client_secret)


def load_bootstrap_credentials(path: Path) -> PolarisCredentials:
    return parse_credentials_payload(
        json.loads(path.read_text(encoding="utf-8")),
        "Polaris bootstrap credentials",
    )


def load_runtime_credentials(path: Path) -> PolarisCredentials:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") == PENDING_RUNTIME_CREDENTIALS_STATUS:
        raise ValueError("Polaris runtime credentials are pending principal provisioning")
    return parse_credentials_payload(payload, "Polaris runtime credentials")


def runtime_credentials_are_pending(path: Path | None) -> bool:
    if path is None or not path.exists():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("status") == PENDING_RUNTIME_CREDENTIALS_STATUS


def credentials_payload(credentials: PolarisCredentials) -> dict[str, dict[str, str]]:
    return {
        credentials.realm: {
            "client-id": credentials.client_id,
            "client-secret": credentials.client_secret,
        }
    }


def write_credentials_file(path: Path, credentials: PolarisCredentials) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(credentials_payload(credentials), separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def join_url(base_url: str, *segments: str) -> str:
    return "/".join((base_url.rstrip("/"), *(segment.strip("/") for segment in segments)))


def encode_path_part(value: str) -> str:
    return quote(value, safe="")


def namespace_parts(namespace: str) -> list[str]:
    parts = [part for part in namespace.split(".") if part]
    if not parts:
        raise ValueError("namespace must not be empty")
    return parts


def encode_namespace(namespace: str) -> str:
    return encode_path_part(UNIT_SEPARATOR.join(namespace_parts(namespace)))
