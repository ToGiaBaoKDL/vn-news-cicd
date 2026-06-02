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

write_seaweedfs_s3_config() {
  local config_path="${SEAWEEDFS_S3_CONFIG_HOST_FILE:-$deploy_root/secrets/seaweedfs-s3.json}"

  mkdir -p "$(dirname "$config_path")"
  SEAWEEDFS_S3_CONFIG_HOST_FILE="$config_path" python3 - <<'PY'
import json
import os
from pathlib import Path

config_path = Path(os.environ["SEAWEEDFS_S3_CONFIG_HOST_FILE"])
temporary_path = config_path.with_suffix(f"{config_path.suffix}.tmp")
config = {
    "identities": [
        {
            "name": "vn-news-ingestion",
            "credentials": [
                {
                    "accessKey": os.environ["AWS_ACCESS_KEY_ID"],
                    "secretKey": os.environ["AWS_SECRET_ACCESS_KEY"],
                }
            ],
            "actions": ["Admin", "Read", "Write", "List", "Tagging"],
        }
    ]
}
temporary_path.write_text(json.dumps(config), encoding="utf-8")
temporary_path.chmod(0o600)
temporary_path.replace(config_path)
PY
  export SEAWEEDFS_S3_CONFIG_HOST_FILE="$config_path"
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

    if ! command -v python3 >/dev/null; then
      echo "python3 is required on the platform node" >&2
      exit 1
    fi

    write_seaweedfs_s3_config
    "${platform_compose[@]}" pull
    "${platform_compose[@]}" up -d --wait \
      airflow-db docker-socket-proxy redpanda redpanda-console seaweedfs-s3

    (
      cd "$cicd_root"
      export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
      uv sync --frozen --all-groups
      uv run python -m scripts.bootstrap_topics \
        --rpk-command "${platform_compose[*]} exec -T redpanda rpk" \
        --brokers redpanda:9092
      uv run python -m scripts.register_event_schemas
      uv run python -m scripts.bootstrap_storage
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
