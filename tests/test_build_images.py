from __future__ import annotations

import pytest
from scripts.build_images import validate_tag


@pytest.mark.parametrize("tag", ["0.1.0", "2026-06-02.1", "sha-a1b2c3d"])
def test_validate_tag_accepts_immutable_tags(tag: str) -> None:
    validate_tag(tag, push=True)


def test_validate_tag_rejects_latest_for_publish() -> None:
    with pytest.raises(ValueError, match="immutable release tag"):
        validate_tag("latest", push=True)


def test_validate_tag_allows_latest_for_local_build() -> None:
    validate_tag("latest", push=False)


def test_validate_tag_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="Invalid Docker image tag"):
        validate_tag("../escape", push=False)
