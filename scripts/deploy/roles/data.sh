#!/usr/bin/env bash

deploy_data_role() {
  checkout_config_repo
  checkout_platform_lib_repo
  set_config_paths
  require_command uv
  require_command python3

  : "${VN_NEWS_REDPANDA_BOOTSTRAP_SERVERS:?set VN_NEWS_REDPANDA_BOOTSTRAP_SERVERS}"
  : "${VN_NEWS_SCHEMA_REGISTRY_URL:?set VN_NEWS_SCHEMA_REGISTRY_URL}"
  : "${VN_NEWS_STORAGE_ENDPOINT_URL:?set VN_NEWS_STORAGE_ENDPOINT_URL}"

  materialize_runtime_secrets
  deploy_redpanda
  deploy_seaweedfs
  prepare_cicd_python
  bootstrap_event_bus
  bootstrap_storage
  deploy_data_access
  configure_host_operations
}
