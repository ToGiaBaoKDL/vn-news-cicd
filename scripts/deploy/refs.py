from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from scripts.images.tags import validate_tag

REPOSITORIES = (
    "vn-news-app",
    "vn-news-cicd",
    "vn-news-config",
    "vn-news-infra",
    "vn-news-orchestration",
    "vn-news-pipelines",
    "vn-news-platform-lib",
    "vn-news-services",
)


def is_commit_ref(ref: str) -> bool:
    return len(ref) == 40 and all(character in "0123456789abcdef" for character in ref.lower())


def git_command() -> list[str]:
    command = ["git"]
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        command.extend(["-c", f"http.extraHeader=Authorization: Bearer {github_token}"])
    return command


def git_fetch_commit(repo_url: str, commit_ref: str, work_dir: Path) -> None:
    subprocess.run(["git", "init", "--quiet", str(work_dir)], check=True)
    subprocess.run(["git", "-C", str(work_dir), "remote", "add", "origin", repo_url], check=True)
    subprocess.run(
        [
            *git_command(),
            "-C",
            str(work_dir),
            "fetch",
            "--quiet",
            "--depth=1",
            "origin",
            commit_ref,
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(work_dir), "cat-file", "-e", f"{commit_ref}^{{commit}}"],
        check=True,
    )


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
            raise ValueError(f"Ref override must use repo=ref: {entry}")
        repo_name, ref = (part.strip() for part in entry.split("=", maxsplit=1))
        if repo_name not in REPOSITORIES:
            raise ValueError(f"Unknown repository override: {repo_name}")
        if not ref:
            raise ValueError(f"Ref override is empty for {repo_name}")
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
        if len(parts) >= 2 and is_commit_ref(parts[0]):
            return parts[0]
    return None


def resolve_remote_ref(owner: str, repo_name: str, ref: str) -> str:
    repo_url = f"https://github.com/{owner}/{repo_name}.git"
    if is_commit_ref(ref):
        ref = ref.lower()
        with tempfile.TemporaryDirectory(prefix="vn-news-deploy-ref-") as tmp_dir:
            git_fetch_commit(repo_url, ref, Path(tmp_dir) / repo_name)
        return ref

    for candidate in remote_ref_candidates(ref):
        commit_ref = ls_remote(repo_url, candidate)
        if commit_ref:
            return commit_ref
    raise ValueError(f"{repo_name} ref is not resolvable from GitHub: {ref}")


def image_tag_from_manifest(image_tag: str, image_manifest: str) -> str:
    explicit_tag = image_tag.strip()
    manifest = image_manifest.strip()
    if explicit_tag and manifest:
        raise ValueError("Use either image_tag or image_manifest, not both")
    if explicit_tag:
        validate_tag(explicit_tag, push=True)
        return explicit_tag
    if not manifest:
        raise ValueError("image_tag or image_manifest is required; deploy does not build images")

    if manifest.startswith("{"):
        payload = json.loads(manifest)
        if not isinstance(payload, dict):
            raise ValueError("image_manifest JSON must be an object")
        manifest_tag = payload.get("image_tag") or payload.get("tag")
    else:
        manifest_tag = parse_text_manifest_image_tag(manifest)

    if not isinstance(manifest_tag, str) or not manifest_tag.strip():
        raise ValueError("image_manifest must define image_tag")
    resolved_tag = manifest_tag.strip()
    validate_tag(resolved_tag, push=True)
    return resolved_tag


def parse_text_manifest_image_tag(manifest: str) -> str:
    entries = [
        entry.strip()
        for chunk in manifest.splitlines()
        for entry in chunk.split(",")
        if entry.strip()
    ]
    if len(entries) == 1 and "=" not in entries[0] and ":" not in entries[0]:
        return entries[0]

    values: dict[str, str] = {}
    for entry in entries:
        if "=" in entry:
            key, value = entry.split("=", maxsplit=1)
        elif ":" in entry:
            key, value = entry.split(":", maxsplit=1)
        else:
            raise ValueError(f"Invalid image_manifest entry: {entry}")
        values[key.strip()] = value.strip()
    return values.get("image_tag") or values.get("tag") or ""


def resolve_deploy_refs(
    *,
    owner: str,
    default_ref: str,
    ref_overrides: dict[str, str],
    image_tag: str,
    image_manifest: str,
) -> tuple[str, dict[str, str]]:
    repositories = {
        repo_name: resolve_remote_ref(owner, repo_name, ref_overrides.get(repo_name, default_ref))
        for repo_name in REPOSITORIES
    }
    return image_tag_from_manifest(image_tag, image_manifest), repositories


def write_github_output(image_tag: str, repositories: dict[str, str], path: Path) -> None:
    lines = [f"image_tag={image_tag}"]
    lines.extend(
        f"{repository.replace('-', '_')}_ref={commit_ref}"
        for repository, commit_ref in sorted(repositories.items())
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve production deployment refs.")
    parser.add_argument("--default-ref", default="main")
    parser.add_argument("--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "ToGiaBaoKDL"))
    parser.add_argument("--ref", action="append", default=[], help="Override repo ref: repo=ref")
    parser.add_argument("--refs", default="", help="Comma or newline separated repo=ref overrides.")
    parser.add_argument("--image-tag", default="")
    parser.add_argument("--image-manifest", default="")
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image_tag, repositories = resolve_deploy_refs(
        owner=args.owner,
        default_ref=args.default_ref,
        ref_overrides=parse_ref_overrides(args.ref, args.refs),
        image_tag=args.image_tag.strip(),
        image_manifest=args.image_manifest.strip(),
    )
    if args.github_output:
        write_github_output(image_tag, repositories, args.github_output)
    print(f"image_tag={image_tag}")
    for repo_name, commit_ref in sorted(repositories.items()):
        print(f"{repo_name}={commit_ref}")


if __name__ == "__main__":
    main()
