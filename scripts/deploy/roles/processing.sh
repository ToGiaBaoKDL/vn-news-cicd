#!/usr/bin/env bash

deploy_processing_role() {
  reset_role_state
  materialize_role_secrets
  configure_role_operations
  deploy_ingestion_workers
  deploy_spark_worker
  validate_spark_worker_registered
}
