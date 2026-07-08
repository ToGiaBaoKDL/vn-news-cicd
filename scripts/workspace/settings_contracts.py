from __future__ import annotations

from news_platform.config import load_settings, load_sources


def validate_settings_load() -> None:
    settings = load_settings()
    sources = load_sources(settings=settings)
    if not settings.get("project", {}).get("name"):
        raise ValueError("settings.yaml must define project.name")
    if not sources:
        raise ValueError("source configuration must contain at least one source")
