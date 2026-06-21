from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

from scripts.paths import CICD_ROOT
from scripts.release.manifest import (
    COMMIT_REF_PATTERN,
    RELEASES_ROOT,
    REQUIRED_REPOSITORIES,
    load_release_manifest,
)
from scripts.release.refs import git_fetch_commit
from scripts.release.tags import validate_tag


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a coordinated release manifest.")
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--image-tag")
    parser.add_argument("--default-ref", default="main")
    parser.add_argument("--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "ToGiaBaoKDL"))
    parser.add_argument("--ref", action="append", default=[], help="Override repo ref: repo=ref")
    parser.add_argument("--refs", default="", help="Comma or newline separated repo=ref overrides.")
    parser.add_argument("--output")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def git_command() -> list[str]:
    command = ["git"]
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        command.extend(["-c", f"http.extraHeader=Authorization: Bearer {github_token}"])
    return command


def parse_ref_overrides(refs: list[str], refs_text: str) -> dict[str, str]:
    entries = list(refs)
    entries.extend(
        entry.strip()
        for chunk in refs_text.splitlines()
        for entry in chunk.split(",")
        if entry.strip()
    )

    overrides: dict[str, str] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"Release ref override must use repo=ref: {entry}")
        repo_name, ref = (part.strip() for part in entry.split("=", maxsplit=1))
        if repo_name not in REQUIRED_REPOSITORIES:
            raise ValueError(f"Unknown release repository override: {repo_name}")
        if not ref:
            raise ValueError(f"Release ref override is empty for {repo_name}")
        overrides[repo_name] = ref
    return overrides


def remote_ref_candidates(ref: str) -> tuple[str, ...]:
    if ref == "HEAD" or ref.startswith("refs/"):
        return (ref,)
    return (
        f"refs/heads/{ref}",
        f"refs/tags/{ref}^{{}}",
        f"refs/tags/{ref}",
        ref,
    )


def ls_remote(repo_url: str, ref: str) -> str | None:
    result = subprocess.run(
        [*git_command(), "ls-remote", repo_url, ref],
        check=True,
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and COMMIT_REF_PATTERN.fullmatch(parts[0]):
            return parts[0]
    return None


def resolve_remote_ref(owner: str, repo_name: str, ref: str) -> str:
    repo_url = f"https://github.com/{owner}/{repo_name}.git"
    if COMMIT_REF_PATTERN.fullmatch(ref):
        with tempfile.TemporaryDirectory(prefix="vn-news-prepare-release-") as tmp_dir:
            git_fetch_commit(repo_url, ref, Path(tmp_dir) / repo_name)
        return ref

    for candidate in remote_ref_candidates(ref):
        commit_ref = ls_remote(repo_url, candidate)
        if commit_ref:
            return commit_ref
    raise ValueError(f"{repo_name} ref is not resolvable from GitHub: {ref}")


def release_manifest_path(release_tag: str, output: str | None) -> Path:
    path = Path(output) if output else RELEASES_ROOT / f"{release_tag}.toml"
    if not path.is_absolute():
        path = CICD_ROOT / path
    path = path.resolve()
    if path.parent != RELEASES_ROOT.resolve():
        raise ValueError("release manifest output must be a file under releases/")
    return path


def render_manifest(
    *,
    release_tag: str,
    image_tag: str,
    repositories: dict[str, str],
) -> str:
    lines = [
        "version = 1",
        f'release_tag = "{release_tag}"',
        f'image_tag = "{image_tag}"',
        "",
        "[repositories]",
    ]
    lines.extend(
        f'{repo_name} = "{repositories[repo_name]}"' for repo_name in REQUIRED_REPOSITORIES
    )
    return "\n".join(lines) + "\n"


def prepare_release(
    *,
    release_tag: str,
    image_tag: str,
    default_ref: str,
    owner: str,
    ref_overrides: dict[str, str],
    output: str | None,
    overwrite: bool,
) -> Path:
    validate_tag(release_tag, push=True)
    validate_tag(image_tag, push=True)

    path = release_manifest_path(release_tag, output)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Release manifest already exists: {path}")

    repositories = {
        repo_name: resolve_remote_ref(owner, repo_name, ref_overrides.get(repo_name, default_ref))
        for repo_name in REQUIRED_REPOSITORIES
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_manifest(
            release_tag=release_tag,
            image_tag=image_tag,
            repositories=repositories,
        ),
        encoding="utf-8",
    )
    load_release_manifest(path)
    return path


def main() -> None:
    args = parse_args()
    image_tag = args.image_tag or args.release_tag
    output_path = prepare_release(
        release_tag=args.release_tag,
        image_tag=image_tag,
        default_ref=args.default_ref,
        owner=args.owner,
        ref_overrides=parse_ref_overrides(args.ref, args.refs),
        output=args.output,
        overwrite=args.overwrite,
    )
    print(f"prepared release manifest: {output_path.relative_to(CICD_ROOT)}")


if __name__ == "__main__":
    main()
