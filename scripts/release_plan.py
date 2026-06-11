from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts.image_catalog import load_image_catalog
from scripts.release_manifest import (
    CICD_ROOT,
    ReleaseManifest,
    load_release_manifest,
    resolve_release_manifest,
)


@dataclass(frozen=True)
class ReleasePlan:
    base_manifest: str
    base_image_tag: str
    changed_repositories: list[str]
    build_images: list[str]
    copy_images: list[str]
    deploy_data: bool
    deploy_control: bool
    deploy_processing: bool


def image_dependencies(image: dict) -> set[str]:
    build = image["build"]
    dependencies = {build["repo"]}
    for context_path in build.get("additional_contexts", {}).values():
        root = str(context_path).split("/", maxsplit=1)[0]
        if root.startswith("vn-news-"):
            dependencies.add(root)
    return dependencies


def image_dependency_map(catalog: dict) -> dict[str, set[str]]:
    return {
        image_key: image_dependencies(image)
        for image_key, image in sorted(catalog["images"].items())
    }


def semver_key(tag: str) -> tuple[int, ...] | None:
    parts = tag.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def previous_manifest_path(current_manifest_path: Path) -> Path | None:
    current = load_release_manifest(current_manifest_path)
    current_key = semver_key(current.release_tag)
    if current_key is None:
        return None

    candidates: list[tuple[tuple[int, ...], Path]] = []
    for path in sorted(current_manifest_path.parent.glob("*.toml")):
        if path == current_manifest_path:
            continue
        try:
            candidate = load_release_manifest(path)
        except (OSError, ValueError):
            continue
        candidate_key = semver_key(candidate.release_tag)
        if candidate_key is not None and candidate_key < current_key:
            candidates.append((candidate_key, path))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def changed_repositories(
    current: ReleaseManifest,
    base: ReleaseManifest | None,
) -> list[str]:
    if base is None:
        return sorted(current.repositories)
    changed = []
    for repo_name, commit_ref in current.repositories.items():
        base_ref = base.repositories.get(repo_name)
        if base_ref == commit_ref:
            continue
        if repo_name == "vn-news-cicd" and not repository_has_functional_changes(
            repo_name,
            base_ref,
            commit_ref,
        ):
            continue
        changed.append(repo_name)
    return sorted(changed)


def repository_has_functional_changes(
    repo_name: str, base_ref: str | None, commit_ref: str
) -> bool:
    if repo_name != "vn-news-cicd" or not base_ref:
        return True
    result = subprocess.run(
        ["git", "-C", str(CICD_ROOT), "diff", "--name-only", base_ref, commit_ref, "--"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return True
    changed_paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return any(not path.startswith("releases/") for path in changed_paths)


def planned_images(
    *,
    catalog: dict,
    current: ReleaseManifest,
    base: ReleaseManifest | None,
    changed_repos: set[str],
) -> tuple[list[str], list[str]]:
    image_keys = sorted(catalog["images"])
    if base is None:
        return image_keys, []

    if not changed_repos:
        return [], []

    if current.image_tag == base.image_tag:
        if image_repositories_changed(catalog, changed_repos):
            msg = "image-producing repositories changed but image_tag did not change"
            raise ValueError(msg)
        return [], []

    dependencies = image_dependency_map(catalog)
    build_images = [image_key for image_key, repos in dependencies.items() if repos & changed_repos]
    copy_images = [image_key for image_key in image_keys if image_key not in set(build_images)]
    return build_images, copy_images


def image_repositories_changed(catalog: dict, changed_repos: set[str]) -> bool:
    dependencies = image_dependency_map(catalog)
    return any(repos & changed_repos for repos in dependencies.values())


def planned_roles(changed_repos: set[str], *, has_base: bool) -> tuple[bool, bool, bool]:
    if not has_base:
        return True, True, True

    deploy_data = "vn-news-infra" in changed_repos
    deploy_control = bool(
        {
            "vn-news-app",
            "vn-news-config",
            "vn-news-infra",
            "vn-news-orchestration",
            "vn-news-platform-lib",
        }
        & changed_repos
    )
    deploy_processing = bool(
        {
            "vn-news-config",
            "vn-news-infra",
            "vn-news-platform-lib",
            "vn-news-services",
        }
        & changed_repos
    )
    return deploy_data, deploy_control, deploy_processing


def resolve_base_manifest(
    current_manifest_path: Path,
    base_manifest: str | None,
) -> Path | None:
    if base_manifest:
        return resolve_release_manifest(base_manifest)
    return previous_manifest_path(current_manifest_path)


def create_release_plan(
    *,
    current_manifest_path: Path,
    base_manifest_path: Path | None,
    catalog: dict,
) -> ReleasePlan:
    current = load_release_manifest(current_manifest_path)
    base = load_release_manifest(base_manifest_path) if base_manifest_path else None
    changed = changed_repositories(current, base)
    build_images, copy_images = planned_images(
        catalog=catalog,
        current=current,
        base=base,
        changed_repos=set(changed),
    )
    deploy_data, deploy_control, deploy_processing = planned_roles(
        set(changed),
        has_base=base is not None,
    )
    return ReleasePlan(
        base_manifest=base_manifest_path.name if base_manifest_path else "",
        base_image_tag=base.image_tag if base else "",
        changed_repositories=changed,
        build_images=build_images,
        copy_images=copy_images,
        deploy_data=deploy_data,
        deploy_control=deploy_control,
        deploy_processing=deploy_processing,
    )


def csv(values: list[str]) -> str:
    return ",".join(values)


def write_github_output(plan: ReleasePlan, path: Path) -> None:
    lines = [
        f"base_manifest={plan.base_manifest}",
        f"base_image_tag={plan.base_image_tag}",
        f"changed_repositories={csv(plan.changed_repositories)}",
        f"build_images={csv(plan.build_images)}",
        f"copy_images={csv(plan.copy_images)}",
        f"deploy_data={str(plan.deploy_data).lower()}",
        f"deploy_control={str(plan.deploy_control).lower()}",
        f"deploy_processing={str(plan.deploy_processing).lower()}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan release image publishing and deployment.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--base-manifest", default="")
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    current_manifest_path = resolve_release_manifest(args.manifest)
    base_manifest_path = resolve_base_manifest(
        current_manifest_path,
        args.base_manifest or None,
    )
    plan = create_release_plan(
        current_manifest_path=current_manifest_path,
        base_manifest_path=base_manifest_path,
        catalog=load_image_catalog(),
    )
    if args.github_output:
        write_github_output(plan, args.github_output)
    print(f"base_manifest={plan.base_manifest or '(none)'}")
    print(f"base_image_tag={plan.base_image_tag or '(none)'}")
    print(f"changed_repositories={csv(plan.changed_repositories) or '(none)'}")
    print(f"build_images={csv(plan.build_images) or '(none)'}")
    print(f"copy_images={csv(plan.copy_images) or '(none)'}")
    print(
        "deploy_roles="
        f"data:{str(plan.deploy_data).lower()},"
        f"control:{str(plan.deploy_control).lower()},"
        f"processing:{str(plan.deploy_processing).lower()}"
    )


if __name__ == "__main__":
    main()
