#!/usr/bin/env bash

deploy_control_role() {
  local orchestration_ref="${VN_NEWS_DEPLOY_ORCHESTRATION_REF:?orchestration ref is required}"
  local app_ref="${VN_NEWS_DEPLOY_APP_REF:?app ref is required}"

  checkout_repo vn-news-app "$app_ref"
  checkout_pipelines_repo
  export VN_NEWS_ORCHESTRATION_GIT_REF="$orchestration_ref"
  set_role_env_value VN_NEWS_ORCHESTRATION_GIT_REF "$orchestration_ref"

  reset_role_state
  materialize_role_secrets
  configure_role_operations

  deploy_spark_master
  provision_spark
  validate_spark_master
  cleanup_spark

  deploy_airflow
  provision_airflow
  validate_airflow
  cleanup_airflow

  deploy_app
  provision_app
  validate_app
  cleanup_app

  deploy_control_access
  provision_cloudflare
  validate_cloudflare
  cleanup_cloudflare
}
