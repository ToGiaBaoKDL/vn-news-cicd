#!/usr/bin/env bash
# shellcheck disable=SC2154

deploy_app() {
  local app_root="$repos_root/vn-news-app"

  docker compose --env-file "$env_file" -f "$app_root/compose.yaml" pull
  docker compose --env-file "$env_file" -f "$app_root/compose.yaml" up -d --wait
}

provision_app() {
  return 0
}

validate_app() {
  return 0
}

cleanup_app() {
  return 0
}
