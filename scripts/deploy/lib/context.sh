#!/usr/bin/env bash

role="${VN_NEWS_DEPLOY_ROLE:?VN_NEWS_DEPLOY_ROLE is required}"
release_tag="${VN_NEWS_DEPLOY_RELEASE_TAG:?VN_NEWS_DEPLOY_RELEASE_TAG is required}"
infra_ref="${VN_NEWS_DEPLOY_INFRA_REF:?VN_NEWS_DEPLOY_INFRA_REF is required}"
config_ref="${VN_NEWS_DEPLOY_CONFIG_REF:-}"
deploy_root="${VN_NEWS_DEPLOY_ROOT:-$HOME/vn-news-intelligence}"
repos_root="$deploy_root/repos"
repo_owner="${VN_NEWS_GITHUB_OWNER:-ToGiaBaoKDL}"
infra_root="$repos_root/vn-news-infra"
cicd_root="$repos_root/vn-news-cicd"
env_file="${VN_NEWS_ENV_FILE:-/etc/vn-news/env/${role}.env}"

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

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name is required on the $role node" >&2
    exit 1
  fi
}

load_role_env() {
  if [[ ! -f "$env_file" ]]; then
    echo "Missing host configuration: $env_file" >&2
    exit 1
  fi

  set -a
  source "$env_file"
  set +a

  export VN_NEWS_RELEASE_TAG="$release_tag"
  export VN_NEWS_SECRETS_HOST_DIR="${VN_NEWS_SECRETS_HOST_DIR:-/run/vn-news/secrets}"
}

set_role_env_value() {
  local key="$1"
  local value="$2"

  sudo sed -i "/^${key}=/d" "$env_file"
  printf '%s=%s\n' "$key" "$value" | sudo tee -a "$env_file" >/dev/null
}

prepare_deploy_context() {
  mkdir -p "$repos_root"
  checkout_repo vn-news-infra "$infra_ref"
  load_role_env
  set_role_env_value VN_NEWS_RELEASE_TAG "$release_tag"
}

materialize_runtime_secrets() {
  sudo bash -lc "set -euo pipefail; set -a; source '$env_file'; set +a; '$infra_root/scripts/materialize_runtime_secrets.sh' '$role'"
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
    cd "$cicd_root"
    export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
    uv sync --frozen --all-groups
  )
}
