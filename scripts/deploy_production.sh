#!/usr/bin/env bash
set -euo pipefail

role="${1:?role is required}"
release_tag="${2:?release tag is required}"
infra_ref="${3:?infra ref is required}"
config_ref="${4:?config ref is required}"
cicd_ref="${5:?cicd ref is required}"
platform_lib_ref="${6:?platform library ref is required}"

deploy_root="${VN_NEWS_DEPLOY_ROOT:-$HOME/vn-news-intelligence}"
repos_root="$deploy_root/repos"
repo_owner="${VN_NEWS_GITHUB_OWNER:-ToGiaBaoKDL}"

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

mkdir -p "$repos_root"
checkout_repo vn-news-infra "$infra_ref"
checkout_repo vn-news-config "$config_ref"

infra_root="$repos_root/vn-news-infra"
config_root="$repos_root/vn-news-config"
env_file="$infra_root/.env"

if [[ ! -f "$env_file" ]]; then
  echo "Missing host configuration: $env_file" >&2
  exit 1
fi

set -a
source "$env_file"
set +a

export VN_NEWS_CONFIG_DIR="$config_root/configs"
export VN_NEWS_CONFIG_HOST_DIR="$config_root/configs"
export VN_NEWS_RELEASE_TAG="$release_tag"

platform_compose=(docker compose --env-file "$env_file" -f "$infra_root/compose.yaml")
workers_compose=(docker compose --env-file "$env_file" -f "$infra_root/compose.workers.yaml")

case "$role" in
  platform)
    checkout_repo vn-news-cicd "$cicd_ref"
    checkout_repo vn-news-platform-lib "$platform_lib_ref"
    cicd_root="$repos_root/vn-news-cicd"

    if ! command -v uv >/dev/null; then
      echo "uv is required on the platform node" >&2
      exit 1
    fi

    "${platform_compose[@]}" pull
    "${platform_compose[@]}" up -d --wait \
      airflow-db docker-socket-proxy redpanda redpanda-console seaweedfs-s3

    (
      cd "$cicd_root"
      export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
      uv sync --frozen --all-groups
      uv run python scripts/bootstrap_topics.py \
        --rpk-command "${platform_compose[*]} exec -T redpanda rpk" \
        --brokers redpanda:9092
      uv run python scripts/register_event_schemas.py
      uv run python scripts/bootstrap_storage.py
    )

    "${platform_compose[@]}" run --rm --no-deps airflow-scheduler airflow db migrate
    "${platform_compose[@]}" up -d --wait
    ;;
  workers)
    "${workers_compose[@]}" pull
    "${workers_compose[@]}" up -d --wait
    ;;
  *)
    echo "Unknown deployment role: $role" >&2
    exit 1
    ;;
esac
