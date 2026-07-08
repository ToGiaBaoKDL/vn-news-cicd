from __future__ import annotations

import json
import subprocess


def inspect_raw(reference: str) -> dict:
    result = subprocess.run(
        ["docker", "buildx", "imagetools", "inspect", "--raw", reference],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def resolve_digest(reference: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            "--format",
            "{{.Manifest.Digest}}",
            reference,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    digest = result.stdout.strip()
    if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
        raise ValueError(f"Cannot resolve digest for {reference}: {digest}")
    return digest
