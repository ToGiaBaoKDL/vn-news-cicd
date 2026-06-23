#!/usr/bin/env bash

deploy_processing_role() {
  checkout_config_repo
  set_config_paths
  reset_role_state
  materialize_role_secrets
  configure_role_operations
  deploy_ingestion_workers
  deploy_spark_worker
  validate_spark_worker_registered
}
