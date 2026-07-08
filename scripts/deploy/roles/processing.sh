#!/usr/bin/env bash

deploy_processing_role() {
  reset_role_state
  materialize_role_secrets
  configure_role_operations

  deploy_ingestion_workers
  provision_ingestion_workers
  validate_ingestion_workers
  cleanup_ingestion_workers

  deploy_spark_worker
  provision_spark
  validate_spark_worker_registered
  cleanup_spark
}
