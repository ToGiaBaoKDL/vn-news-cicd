#!/usr/bin/env bash

deploy_data_role() {
  materialize_runtime_secrets
  deploy_redpanda
  deploy_seaweedfs
  configure_host_operations
}
