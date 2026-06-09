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
if [[ "$role" == "control" ]]; then
  require_command uv
  require_command python3
fi

docker info >/dev/null 2>&1 || fail "Docker daemon is unavailable"
sudo -n true >/dev/null 2>&1 || fail "passwordless sudo is unavailable"
[[ -r "$env_file" ]] || fail "host configuration is not readable: $env_file"
[[ "$(stat -c '%a' "$env_file")" == "640" ]] || fail "$env_file must have mode 640"
check_disk_usage /

case "$role" in
  data)
    grep -q '^VN_NEWS_RECOVERY_BUCKET=' "$env_file" || fail "VN_NEWS_RECOVERY_BUCKET is not configured"
    require_command mountpoint
    mountpoint -q /srv/vn-news-data || fail "/srv/vn-news-data is not mounted"
    require_directory /srv/vn-news-data/redpanda
    require_directory /srv/vn-news-data/seaweedfs
    check_disk_usage /srv/vn-news-data
    ;;
  control)
    grep -q '^VN_NEWS_RECOVERY_BUCKET=' "$env_file" || fail "VN_NEWS_RECOVERY_BUCKET is not configured"
    require_directory /srv/vn-news-control/airflow-db
    require_directory /srv/vn-news-control/airflow-dag-bundles
    require_directory /srv/vn-news-control/airflow-logs
    ;;
  processing)
    require_directory /srv/vn-news-processing
    ;;
esac

echo "preflight ok: $role"
