#!/usr/bin/env bash
set -euo pipefail

role="${1:?role is required}"
env_file="${VN_NEWS_ENV_FILE:-/etc/vn-news/env/${role}.env}"
max_disk_percent="${VN_NEWS_PREFLIGHT_MAX_DISK_PERCENT:-85}"

fail() {
  echo "preflight failed: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

require_directory() {
  [[ -d "$1" ]] || fail "missing directory: $1"
}

require_env_value() {
  [[ -n "${!1:-}" ]] || fail "$1 is not configured"
}

check_disk_usage() {
  local path="$1"
  local usage

  usage="$(df -P "$path" | awk 'NR == 2 {gsub("%", "", $5); print $5}')"
  [[ "$usage" =~ ^[0-9]+$ ]] || fail "could not read disk usage: $path"
  ((usage < max_disk_percent)) || fail "$path disk usage is ${usage}%"
}

case "$role" in
  data | control | processing) ;;
  *) fail "unknown role: $role" ;;
esac

for command_name in docker git sudo; do
  require_command "$command_name"
done
if [[ "$role" == "data" ]]; then
  require_command uv
  require_command python3
fi
if [[ "$role" == "control" || "$role" == "processing" ]]; then
  require_command curl
  require_command python3
fi
docker info >/dev/null 2>&1 || fail "Docker daemon is unavailable"
sudo -n true >/dev/null 2>&1 || fail "passwordless sudo is unavailable"
[[ -r "$env_file" ]] || fail "host configuration is not readable: $env_file"
[[ "$(stat -c '%a' "$env_file")" == "640" ]] || fail "$env_file must have mode 640"
set -a
# shellcheck disable=SC1090
source "$env_file"
set +a
check_disk_usage /

case "$role" in
  data)
    require_env_value VN_NEWS_RECOVERY_BUCKET
    require_env_value VN_NEWS_REDPANDA_BOOTSTRAP_SERVERS
    require_env_value VN_NEWS_SCHEMA_REGISTRY_URL
    require_env_value VN_NEWS_STORAGE_ENDPOINT_URL
    require_env_value VN_NEWS_POLARIS_CATALOG_URL
    require_env_value VN_NEWS_POLARIS_REALM
    require_env_value VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID
    require_env_value VN_NEWS_SEAWEEDFS_S3_CONFIG_SECRET_OCID
    require_env_value VN_NEWS_STORAGE_ADMIN_S3_CREDENTIALS_SECRET_OCID
    require_env_value VN_NEWS_POLARIS_DB_PASSWORD_SECRET_OCID
    require_env_value VN_NEWS_POLARIS_BOOTSTRAP_ADMIN_SECRET_OCID
    require_env_value VN_NEWS_CLOUDFLARE_DATA_TUNNEL_TOKEN_SECRET_OCID
    require_command mountpoint
    mountpoint -q /srv/vn-news-data || fail "/srv/vn-news-data is not mounted"
    require_directory /srv/vn-news-data/redpanda
    require_directory /srv/vn-news-data/seaweedfs
    require_directory /srv/vn-news-data/polaris-postgres
    check_disk_usage /srv/vn-news-data
    ;;
  control)
    require_env_value VN_NEWS_CONTROL_PRIVATE_IP
    require_env_value VN_NEWS_SPARK_IMAGE
    require_env_value VN_NEWS_SPARK_MASTER_PORT
    require_env_value VN_NEWS_SPARK_MASTER_UI_PORT
    require_env_value VN_NEWS_SPARK_DRIVER_PORT
    require_env_value VN_NEWS_SPARK_BLOCK_MANAGER_PORT
    require_env_value VN_NEWS_SPARK_CHECKPOINT_ROOT
    require_env_value VN_NEWS_POLARIS_CATALOG_URL
    require_env_value VN_NEWS_POLARIS_REALM
    require_env_value VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID
    require_env_value VN_NEWS_SPARK_RPC_AUTH_SECRET_OCID
    require_env_value VN_NEWS_RECOVERY_BUCKET
    require_env_value VN_NEWS_INGESTION_S3_CREDENTIALS_SECRET_OCID
    require_env_value VN_NEWS_AIRFLOW_DB_PASSWORD_SECRET_OCID
    require_env_value VN_NEWS_AIRFLOW_API_JWT_SECRET_OCID
    require_env_value VN_NEWS_AIRFLOW_FERNET_KEY_SECRET_OCID
    require_env_value VN_NEWS_AIRFLOW_ADMIN_PASSWORD_SECRET_OCID
    require_env_value VN_NEWS_AIRFLOW_EXPECTED_DAG_ID
    require_env_value VN_NEWS_CLOUDFLARE_CONTROL_TUNNEL_TOKEN_SECRET_OCID
    require_directory /srv/vn-news-control/airflow-db
    require_directory /srv/vn-news-control/airflow-dag-bundles
    require_directory /srv/vn-news-control/airflow-logs
    require_directory "$VN_NEWS_SPARK_CHECKPOINT_ROOT"
    ;;
  processing)
    require_env_value VN_NEWS_PROCESSING_PRIVATE_IP
    require_env_value VN_NEWS_STORAGE_ENDPOINT_URL
    require_env_value VN_NEWS_SPARK_IMAGE
    require_env_value VN_NEWS_SPARK_MASTER_URL
    require_env_value VN_NEWS_SPARK_MASTER_UI_PORT
    require_env_value VN_NEWS_SPARK_WORKER_PORT
    require_env_value VN_NEWS_SPARK_WORKER_UI_PORT
    require_env_value VN_NEWS_SPARK_WORKER_CORES
    require_env_value VN_NEWS_SPARK_WORKER_MEMORY
    require_env_value VN_NEWS_SPARK_WORKER_DIR
    require_env_value VN_NEWS_SPARK_LOCAL_DIR
    require_env_value VN_NEWS_SPARK_RPC_AUTH_SECRET_OCID
    require_env_value VN_NEWS_INGESTION_S3_CREDENTIALS_SECRET_OCID
    require_directory /srv/vn-news-processing
    require_directory "$VN_NEWS_SPARK_WORKER_DIR"
    require_directory "$VN_NEWS_SPARK_LOCAL_DIR"
    ;;
esac

echo "preflight ok: $role"
