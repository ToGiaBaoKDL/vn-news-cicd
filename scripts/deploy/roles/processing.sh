#!/usr/bin/env bash

deploy_processing_role() {
  checkout_config_repo
  set_config_paths
  materialize_runtime_secrets
  deploy_workers
}
