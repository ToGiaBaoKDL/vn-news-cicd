from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import yaml

from scripts.paths import CICD_ROOT, WORKSPACE_ROOT

APP_ROOT = WORKSPACE_ROOT / "vn-news-app"
CONFIG_ROOT = WORKSPACE_ROOT / "vn-news-config"
INFRA_ROOT = WORKSPACE_ROOT / "vn-news-infra"
ORCHESTRATION_ROOT = WORKSPACE_ROOT / "vn-news-orchestration"
PIPELINES_ROOT = WORKSPACE_ROOT / "vn-news-pipelines"
PLATFORM_LIB_ROOT = WORKSPACE_ROOT / "vn-news-platform-lib"
SERVICES_ROOT = WORKSPACE_ROOT / "vn-news-services"

REPOSITORY_ROOTS = (
    APP_ROOT,
    CICD_ROOT,
    CONFIG_ROOT,
    INFRA_ROOT,
    ORCHESTRATION_ROOT,
    PIPELINES_ROOT,
    PLATFORM_LIB_ROOT,
    SERVICES_ROOT,
)
REPOSITORY_NAMES = (
    "vn-news-app",
    "vn-news-cicd",
    "vn-news-config",
    "vn-news-infra",
    "vn-news-orchestration",
    "vn-news-pipelines",
    "vn-news-platform-lib",
    "vn-news-services",
)
DEPLOY_ROLES = ("data", "control", "processing")


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def read_env_template(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", maxsplit=1)
        values[key] = value
    return values


def missing_keys(required: set[str], values: Iterable[str]) -> list[str]:
    return sorted(required - set(values))


def duplicate_values(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)
