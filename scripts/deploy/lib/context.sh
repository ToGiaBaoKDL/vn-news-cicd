#!/usr/bin/env bash
# shellcheck disable=SC2030,SC2031

role="${VN_NEWS_DEPLOY_ROLE:?VN_NEWS_DEPLOY_ROLE is required}"
image_manifest="${VN_NEWS_IMAGE_MANIFEST:?VN_NEWS_IMAGE_MANIFEST is required}"
infra_ref="${VN_NEWS_DEPLOY_INFRA_REF:?VN_NEWS_DEPLOY_INFRA_REF is required}"
config_ref="${VN_NEWS_DEPLOY_CONFIG_REF:-}"
platform_lib_ref="${VN_NEWS_DEPLOY_PLATFORM_LIB_REF:-}"
pipelines_ref="${VN_NEWS_DEPLOY_PIPELINES_REF:-}"
deploy_root="${VN_NEWS_DEPLOY_ROOT:-$HOME/vn-news-intelligence}"
repos_root="$deploy_root/repos"
repo_owner="${VN_NEWS_GITHUB_OWNER:-ToGiaBaoKDL}"
infra_root="$repos_root/vn-news-infra"
cicd_root="$repos_root/vn-news-cicd"
env_file="${VN_NEWS_ENV_FILE:-/etc/vn-news/env/${role}.env}"
deployment_metadata_file="${VN_NEWS_DEPLOYMENT_METADATA_FILE:-/etc/vn-news/deployment.json}"
legacy_image_env_keys=(
  VN_NEWS_IMAGE_TAG
  VN_NEWS_IMAGE_REGISTRY
  VN_NEWS_IMAGE_NAMESPACE
  VN_NEWS_APP_IMAGE_TAG
  VN_NEWS_DEPLOY_IMAGE_TAG
  VN_NEWS_INFRA_IMAGE_TAG
  VN_NEWS_SERVICES_IMAGE_TAG
)

checkout_repo() {
  local repo_name="$1"
  local commit_ref="$2"
  local repo_dir="$repos_root/$repo_name"

  if [[ ! -d "$repo_dir/.git" ]]; then
    git clone "https://github.com/$repo_owner/$repo_name.git" "$repo_dir"
  fi
  git -C "$repo_dir" fetch --quiet origin "$commit_ref"
  git -C "$repo_dir" checkout --quiet --detach "$commit_ref"
}

checkout_config_repo() {
  if [[ -z "$config_ref" ]]; then
    echo "config ref is required for role: $role" >&2
    exit 1
  fi
  checkout_repo vn-news-config "$config_ref"
}

checkout_platform_lib_repo() {
  if [[ -z "$platform_lib_ref" ]]; then
    echo "platform lib ref is required for role: $role" >&2
    exit 1
  fi
  checkout_repo vn-news-platform-lib "$platform_lib_ref"
}

checkout_pipelines_repo() {
  if [[ -z "$pipelines_ref" ]]; then
    echo "pipelines ref is required for role: $role" >&2
    exit 1
  fi
  checkout_repo vn-news-pipelines "$pipelines_ref"
}

load_role_env() {
  if [[ ! -f "$env_file" ]]; then
    echo "Missing host configuration: $env_file" >&2
    exit 1
  fi

  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a

  export VN_NEWS_IMAGE_MANIFEST="$image_manifest"
  export VN_NEWS_SECRETS_HOST_DIR="${VN_NEWS_SECRETS_HOST_DIR:-/run/vn-news/secrets}"
}

load_image_env() {
  if [[ ! -f "$cicd_root/images.yaml" ]]; then
    echo "Missing image catalog: $cicd_root/images.yaml" >&2
    exit 1
  fi

  local image_env_tmp
  cleanup_image_env
  image_env_tmp="$(mktemp)"
  run_cicd_module scripts.images.manifest \
    --manifest "$image_manifest" \
    --role "$role" \
    --format shell >"$image_env_tmp"
  set -a
  # shellcheck disable=SC1090
  source "$image_env_tmp"
  set +a
  while IFS= read -r line; do
    [[ "$line" == export\ * ]] || continue
    local assignment="${line#export }"
    local key="${assignment%%=*}"
    set_role_env_value "$key" "${!key}"
  done <"$image_env_tmp"
  rm -f "$image_env_tmp"
}

require_file() {
  local path="$1"
  local label="$2"

  if [[ ! -f "$path" ]]; then
    echo "Missing $label: $path" >&2
    exit 1
  fi
}

set_role_env_value() {
  local key="$1"
  local value="$2"

  remove_role_env_value "$key"
  printf '%s=%q\n' "$key" "$value" | sudo tee -a "$env_file" >/dev/null
}

remove_role_env_value() {
  local key="$1"

  sudo sed -i "/^${key}=/d" "$env_file"
}

cleanup_image_env() {
  local image_env_names_tmp key

  cleanup_legacy_image_env
  image_env_names_tmp="$(mktemp)"
  run_cicd_module scripts.images.manifest \
    --format cleanup-env-names >"$image_env_names_tmp"
  while IFS= read -r key; do
    [[ -n "$key" ]] || continue
    remove_role_env_value "$key"
  done <"$image_env_names_tmp"
  rm -f "$image_env_names_tmp"
}

cleanup_legacy_image_env() {
  local key

  for key in "${legacy_image_env_keys[@]}"; do
    remove_role_env_value "$key"
  done
}

prepare_deploy_context() {
  mkdir -p "$repos_root"
  checkout_repo vn-news-infra "$infra_ref"
  checkout_config_repo
  checkout_platform_lib_repo
  load_role_env
  set_config_paths
  prepare_cicd_python
  load_image_env
  echo "deployment context: role=$role images=$VN_NEWS_IMAGE_MANIFEST"
}

repo_commit() {
  local repo_name="$1"
  local repo_dir="$repos_root/$repo_name"

  if [[ -d "$repo_dir/.git" ]]; then
    git -C "$repo_dir" rev-parse HEAD
  fi
}

write_deployment_metadata() {
  local metadata_tmp deployed_at repo_name commit_ref repositories
  local -a repo_names

  deployed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  metadata_tmp="$(mktemp)"
  repositories=""
  case "$role" in
    data)
      repo_names=(vn-news-cicd vn-news-config vn-news-infra vn-news-platform-lib)
      ;;
    control)
      repo_names=(
        vn-news-app
        vn-news-cicd
        vn-news-config
        vn-news-infra
        vn-news-pipelines
        vn-news-platform-lib
      )
      ;;
    processing)
      repo_names=(vn-news-cicd vn-news-config vn-news-infra vn-news-platform-lib)
      ;;
  esac

  for repo_name in "${repo_names[@]}"; do
    commit_ref="$(repo_commit "$repo_name")"
    [[ -n "$commit_ref" ]] || continue
    repositories+="${repo_name}=${commit_ref}"$'\n'
  done

  VN_NEWS_DEPLOY_METADATA_DEPLOYED_AT="$deployed_at" \
    VN_NEWS_DEPLOY_METADATA_REPOSITORIES="$repositories" \
    python3 - "$metadata_tmp" <<'PY'
import json
import os
import sys
from pathlib import Path

repositories = {}
for line in os.environ.get("VN_NEWS_DEPLOY_METADATA_REPOSITORIES", "").splitlines():
    repo_name, commit_ref = line.split("=", maxsplit=1)
    repositories[repo_name] = commit_ref

payload = {
    "role": os.environ["VN_NEWS_DEPLOY_ROLE"],
    "image_manifest": json.loads(os.environ["VN_NEWS_IMAGE_MANIFEST"]),
    "deployed_at": os.environ["VN_NEWS_DEPLOY_METADATA_DEPLOYED_AT"],
    "repositories": repositories,
}
if os.environ["VN_NEWS_DEPLOY_ROLE"] == "control":
    payload["configured_refs"] = {
        "vn-news-orchestration": os.environ.get("VN_NEWS_DEPLOY_ORCHESTRATION_REF", "")
    }

Path(sys.argv[1]).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

  sudo install -d -m 0755 "$(dirname "$deployment_metadata_file")"
  sudo install -m 0644 "$metadata_tmp" "$deployment_metadata_file"
  rm -f "$metadata_tmp"
}

materialize_role_secrets() {
  sudo bash -lc "set -euo pipefail; set -a; source '$env_file'; set +a; '$infra_root/scripts/secrets/materialize.sh' '$role'"
}

configure_role_operations() {
  sudo "$infra_root/scripts/host/configure_operations.sh" "$role" "$deploy_root"
}

reset_role_state() {
  if [[ "${VN_NEWS_DEPLOY_RESET:-0}" != "1" ]]; then
    return
  fi

  sudo "$infra_root/scripts/host/reset_role.sh" "$role" --wipe-data --force
}

compose_data() {
  docker compose --env-file "$env_file" -f "$infra_root/compose.data.yaml" "$@"
}

compose_control() {
  docker compose --env-file "$env_file" -f "$infra_root/compose.control.yaml" "$@"
}

compose_processing() {
  docker compose --env-file "$env_file" -f "$infra_root/compose.processing.yaml" "$@"
}

set_config_paths() {
  local config_root="$repos_root/vn-news-config"

  export VN_NEWS_CONFIG_DIR="$config_root/configs"
  export VN_NEWS_CONFIG_HOST_DIR="$config_root/configs"
}

prepare_cicd_python() {
  (
    cd "$cicd_root" || exit
    export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
    uv sync --frozen --no-dev
  )
}

run_cicd_module() {
  (
    cd "$cicd_root" || exit
    export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
    uv run --no-dev python -m "$@"
  )
}
