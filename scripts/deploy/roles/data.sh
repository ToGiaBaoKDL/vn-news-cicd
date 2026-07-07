#!/usr/bin/env bash

deploy_data_role() {
  : "${VN_NEWS_REDPANDA_BOOTSTRAP_SERVERS:?set VN_NEWS_REDPANDA_BOOTSTRAP_SERVERS}"
  : "${VN_NEWS_SCHEMA_REGISTRY_URL:?set VN_NEWS_SCHEMA_REGISTRY_URL}"
  : "${VN_NEWS_STORAGE_ENDPOINT_URL:?set VN_NEWS_STORAGE_ENDPOINT_URL}"
  : "${VN_NEWS_POLARIS_CATALOG_URL:?set VN_NEWS_POLARIS_CATALOG_URL}"

  reset_role_state
  materialize_role_secrets
  configure_role_operations
  deploy_redpanda
  deploy_seaweedfs
  deploy_polaris
  bootstrap_redpanda_topics
  bootstrap_redpanda_schemas
  bootstrap_seaweedfs_buckets
  provision_polaris
  validate_polaris
  deploy_data_access
}
