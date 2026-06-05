from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

from scripts.release_manifest import load_release_manifest, resolve_release_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify release manifest repository refs exist.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "ToGiaBaoKDL"))
    return parser.parse_args()


def git_fetch_commit(repo_url: str, commit_ref: str, work_dir: Path) -> None:
    subprocess.run(["git", "init", "--quiet", str(work_dir)], check=True)
    subprocess.run(["git", "-C", str(work_dir), "remote", "add", "origin", repo_url], check=True)

    fetch_command = ["git"]
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        fetch_command.extend(["-c", f"http.extraHeader=Authorization: Bearer {github_token}"])
    fetch_command.extend(
        [
            "-C",
            str(work_dir),
            "fetch",
            "--quiet",
            "--depth=1",
            "origin",
            commit_ref,
        ]
    )
    subprocess.run(fetch_command, check=True)
    subprocess.run(
        ["git", "-C", str(work_dir), "cat-file", "-e", f"{commit_ref}^{{commit}}"],
        check=True,
    )


def validate_refs(manifest_filename: str, owner: str) -> None:
    manifest = load_release_manifest(resolve_release_manifest(manifest_filename))
    with tempfile.TemporaryDirectory(prefix="vn-news-release-refs-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        for repo_name, commit_ref in sorted(manifest.repositories.items()):
            repo_url = f"https://github.com/{owner}/{repo_name}.git"
            try:
                git_fetch_commit(repo_url, commit_ref, tmp_root / repo_name)
            except subprocess.CalledProcessError as exc:
                raise SystemExit(
                    f"{repo_name} ref is not fetchable from GitHub: {commit_ref}"
                ) from exc
    print(f"release refs ok: {manifest_filename}")


def main() -> None:
    args = parse_args()
    validate_refs(args.manifest, args.owner)


if __name__ == "__main__":
    main()
