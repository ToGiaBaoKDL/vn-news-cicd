from __future__ import annotations

import re

IMAGE_TAG_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")


def validate_tag(tag: str, *, push: bool) -> None:
    if not IMAGE_TAG_PATTERN.fullmatch(tag):
        raise ValueError(f"Invalid Docker image tag: {tag}")
    if push and tag == "latest":
        raise ValueError("Published images must use an immutable release tag")
