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
  : "${VN_NEWS_POLARIS_CATALOG_URL:?set VN_NEWS_POLARIS_CATALOG_URL}"

  reset_role_state
  materialize_role_secrets
  deploy_redpanda
  deploy_seaweedfs
  deploy_polaris
  prepare_cicd_python
  bootstrap_redpanda_topics
  bootstrap_redpanda_schemas
  bootstrap_seaweedfs_buckets
  bootstrap_polaris_catalog
  provision_polaris_access
  validate_polaris_access
  deploy_data_access
  configure_role_operations
}
