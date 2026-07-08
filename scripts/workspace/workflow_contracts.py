from __future__ import annotations

import re
from pathlib import Path

from scripts.workspace.common import REPOSITORY_ROOTS, WORKSPACE_ROOT, load_yaml

ACTION_REF_PATTERN = re.compile(r"uses:\s*([^@\s]+)@([^\s#]+)")
IMMUTABLE_ACTION_REF_PATTERN = re.compile(r"[0-9a-f]{40}")


def validate_workflow_action_ref(path: Path, action: str, ref: str) -> None:
    if action.startswith("./"):
        return
    if not IMMUTABLE_ACTION_REF_PATTERN.fullmatch(ref):
        msg = f"{path} must pin {action} to an immutable commit SHA, not {ref}"
        raise ValueError(msg)


def validate_workflow_action_pins() -> None:
    for root in REPOSITORY_ROOTS:
        workflow_root = root / ".github" / "workflows"
        if not workflow_root.is_dir():
            continue
        for pattern in ("*.yaml", "*.yml"):
            for path in sorted(workflow_root.glob(pattern)):
                load_yaml(path)
                content = path.read_text(encoding="utf-8")
                for action, ref in ACTION_REF_PATTERN.findall(content):
                    validate_workflow_action_ref(path.relative_to(WORKSPACE_ROOT), action, ref)
