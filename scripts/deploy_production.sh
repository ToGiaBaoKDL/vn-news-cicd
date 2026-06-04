#!/usr/bin/env bash
set -euo pipefail

role="${1:?role is required}"
release_tag="${2:?release tag is required}"
infra_ref="${3:?infra ref is required}"
config_ref="${4:-}"

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

checkout_config_repo() {
  if [[ -z "$config_ref" ]]; then
    echo "config ref is required for role: $role" >&2
    exit 1
  fi
  checkout_repo vn-news-config "$config_ref"
}

mkdir -p "$repos_root"
checkout_repo vn-news-infra "$infra_ref"

infra_root="$repos_root/vn-news-infra"
env_file="${VN_NEWS_ENV_FILE:-/etc/vn-news/env/${role}.env}"

if [[ ! -f "$env_file" ]]; then
  echo "Missing host configuration: $env_file" >&2
  exit 1
fi

set -a
source "$env_file"
set +a

export VN_NEWS_RELEASE_TAG="$release_tag"
export VN_NEWS_SECRETS_HOST_DIR="${VN_NEWS_SECRETS_HOST_DIR:-/run/vn-news/secrets}"

materialize_runtime_secrets() {
  "$infra_root/scripts/materialize_runtime_secrets.sh" "$role"
}

compose_data=(docker compose --env-file "$env_file" -f "$infra_root/compose.data.yaml")
compose_control=(docker compose --env-file "$env_file" -f "$infra_root/compose.control.yaml")
compose_processing=(docker compose --env-file "$env_file" -f "$infra_root/compose.processing.yaml")

case "$role" in
  data)
    materialize_runtime_secrets
    "${compose_data[@]}" pull redpanda redpanda-console seaweedfs-s3
    "${compose_data[@]}" up -d --wait redpanda redpanda-console seaweedfs-s3
    ;;
  control)
    cicd_ref="${5:?cicd ref is required}"
    orchestration_ref="${6:?orchestration ref is required}"
    platform_lib_ref="${7:?platform library ref is required}"
    app_ref="${8:?app ref is required}"
    checkout_config_repo
    checkout_repo vn-news-cicd "$cicd_ref"
    checkout_repo vn-news-orchestration "$orchestration_ref"
    checkout_repo vn-news-platform-lib "$platform_lib_ref"
    checkout_repo vn-news-app "$app_ref"
    config_root="$repos_root/vn-news-config"
    cicd_root="$repos_root/vn-news-cicd"
    app_root="$repos_root/vn-news-app"
    export VN_NEWS_CONFIG_DIR="$config_root/configs"
    export VN_NEWS_CONFIG_HOST_DIR="$config_root/configs"
    app_compose=(docker compose --env-file "$env_file" -f "$app_root/compose.yaml")

    if ! command -v uv >/dev/null; then
      echo "uv is required on the control node" >&2
      exit 1
    fi

    if ! command -v python3 >/dev/null; then
      echo "python3 is required on the control node" >&2
      exit 1
    fi

    materialize_runtime_secrets
    "${compose_control[@]}" pull airflow-db docker-socket-proxy airflow-scheduler airflow-dag-processor airflow-api-server
    "${compose_control[@]}" up -d --wait airflow-db
    "${compose_control[@]}" --profile bootstrap run --rm airflow-bootstrap
    "${compose_control[@]}" up -d --wait docker-socket-proxy airflow-scheduler airflow-dag-processor airflow-api-server

    (
      cd "$cicd_root"
      export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
      export AWS_SHARED_CREDENTIALS_FILE="$VN_NEWS_SECRETS_HOST_DIR/ingestion-s3-credentials"
      uv sync --frozen --all-groups
      uv run python -m scripts.bootstrap_topics \
        --rpk-command "docker run --rm ${REDPANDA_IMAGE:-redpandadata/redpanda:v26.1.9} rpk" \
        --brokers "$VN_NEWS_REDPANDA_BOOTSTRAP_SERVERS"
      uv run python -m scripts.register_event_schemas \
        --registry-url "$VN_NEWS_SCHEMA_REGISTRY_URL"
      uv run python -m scripts.bootstrap_storage \
        --endpoint-url "$VN_NEWS_STORAGE_ENDPOINT_URL"
    )

    "${app_compose[@]}" pull
    "${app_compose[@]}" up -d --wait
    ;;
  processing)
    checkout_config_repo
    config_root="$repos_root/vn-news-config"
    export VN_NEWS_CONFIG_DIR="$config_root/configs"
    export VN_NEWS_CONFIG_HOST_DIR="$config_root/configs"
    materialize_runtime_secrets
    "${compose_processing[@]}" pull
    "${compose_processing[@]}" up -d --wait
    ;;
  *)
    echo "Unknown deployment role: $role" >&2
    exit 1
    ;;
esac
