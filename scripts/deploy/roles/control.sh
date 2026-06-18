#!/usr/bin/env bash

deploy_control_role() {
  local orchestration_ref="${VN_NEWS_DEPLOY_ORCHESTRATION_REF:?orchestration ref is required}"
  local app_ref="${VN_NEWS_DEPLOY_APP_REF:?app ref is required}"

  checkout_config_repo
  checkout_repo vn-news-app "$app_ref"
  set_config_paths
  export VN_NEWS_ORCHESTRATION_GIT_REF="$orchestration_ref"
  set_role_env_value VN_NEWS_ORCHESTRATION_GIT_REF "$orchestration_ref"

  materialize_runtime_secrets
  deploy_airflow
  deploy_app
  deploy_control_access
  configure_host_operations
}
