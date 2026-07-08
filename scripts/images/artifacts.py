from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SOURCE_REPOSITORIES = {
    "app": "vn-news-app",
    "infra": "vn-news-infra",
    "services": "vn-news-services",
}


def api_get(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def workflow_runs_url(owner: str, repo: str, branch: str, page: int) -> str:
    query = urllib.parse.urlencode(
        {
            "branch": branch,
            "exclude_pull_requests": "true",
            "per_page": "50",
            "page": str(page),
            "status": "completed",
        }
    )
    return f"https://api.github.com/repos/{owner}/{repo}/actions/runs?{query}"


def run_artifacts_url(owner: str, repo: str, run_id: int) -> str:
    return f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts"


def run_has_artifact(owner: str, repo: str, run_id: int, artifact_name: str, token: str) -> bool:
    payload = api_get(run_artifacts_url(owner, repo, run_id), token)
    return any(
        artifact.get("name") == artifact_name and not artifact.get("expired", False)
        for artifact in payload.get("artifacts", [])
    )


def latest_artifact_run_id(
    *,
    owner: str,
    repo: str,
    branch: str,
    workflow_name: str,
    artifact_name: str,
    token: str,
) -> str:
    for page in range(1, 6):
        payload = api_get(workflow_runs_url(owner, repo, branch, page), token)
        runs = payload.get("workflow_runs", [])
        if not runs:
            break
        for run in runs:
            if run.get("name") != workflow_name or run.get("conclusion") != "success":
                continue
            run_id = int(run["id"])
            if run_has_artifact(owner, repo, run_id, artifact_name, token):
                return str(run_id)
    raise ValueError(f"{repo} has no successful {artifact_name} artifact on {branch}")


def resolve_manifest_run_ids(
    *,
    owner: str,
    branch: str,
    workflow_name: str,
    artifact_name: str,
    token: str,
    provided_run_ids: dict[str, str],
    manual_manifest: str = "",
    base_manifest: str = "",
    base_run_id: str = "",
) -> dict[str, str]:
    should_discover = not manual_manifest.strip() and not base_manifest.strip() and not base_run_id
    resolved: dict[str, str] = {}
    for key, repo in SOURCE_REPOSITORIES.items():
        run_id = provided_run_ids.get(key, "").strip()
        if not run_id and should_discover:
            run_id = latest_artifact_run_id(
                owner=owner,
                repo=repo,
                branch=branch,
                workflow_name=workflow_name,
                artifact_name=artifact_name,
                token=token,
            )
        resolved[key] = run_id
    return resolved


def write_github_output(run_ids: dict[str, str], path: Path) -> None:
    lines = [f"{key}_manifest_run_id={run_id}" for key, run_id in sorted(run_ids.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve image manifest artifact run IDs.")
    parser.add_argument("--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "ToGiaBaoKDL"))
    parser.add_argument("--branch", default="main")
    parser.add_argument("--workflow-name", default="Publish Images")
    parser.add_argument("--artifact-name", default="image-manifest")
    parser.add_argument("--manual-manifest", default="")
    parser.add_argument("--base-manifest", default="")
    parser.add_argument("--base-run-id", default="")
    parser.add_argument("--app-run-id", default="")
    parser.add_argument("--infra-run-id", default="")
    parser.add_argument("--services-run-id", default="")
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise ValueError("GITHUB_TOKEN is required to resolve image manifest artifacts")
    run_ids = resolve_manifest_run_ids(
        owner=args.owner,
        branch=args.branch,
        workflow_name=args.workflow_name,
        artifact_name=args.artifact_name,
        token=token,
        provided_run_ids={
            "app": args.app_run_id,
            "infra": args.infra_run_id,
            "services": args.services_run_id,
        },
        manual_manifest=args.manual_manifest,
        base_manifest=args.base_manifest,
        base_run_id=args.base_run_id,
    )
    if args.github_output:
        write_github_output(run_ids, args.github_output)
    print(json.dumps(run_ids, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
