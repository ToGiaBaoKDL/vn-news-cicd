from __future__ import annotations

import shlex
import subprocess


def split_prefix(value: str) -> list[str]:
    return shlex.split(value)


def command(prefix: list[str], *parts: str, brokers: str) -> list[str]:
    return [*prefix, *parts, "-X", f"brokers={brokers}"]


def run(argv: list[str], *, dry_run: bool) -> None:
    print(shlex.join(argv))
    if not dry_run:
        subprocess.run(argv, check=True)


def capture(argv: list[str]) -> str:
    result = subprocess.run(argv, check=True, capture_output=True, text=True)
    return result.stdout
