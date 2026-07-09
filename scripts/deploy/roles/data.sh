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
  provision_redpanda_schema_registry
  provision_redpanda_topics
  provision_redpanda_schemas
  validate_redpanda
  cleanup_redpanda

  deploy_seaweedfs
  provision_seaweedfs_buckets
  validate_seaweedfs
  cleanup_seaweedfs

  deploy_polaris
  provision_polaris
  validate_polaris
  cleanup_polaris

  deploy_data_access
  provision_cloudflare
  validate_cloudflare
  cleanup_cloudflare
}
