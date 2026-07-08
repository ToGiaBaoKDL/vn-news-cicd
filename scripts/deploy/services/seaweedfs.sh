#!/usr/bin/env bash

deploy_seaweedfs() {
  compose_data pull seaweedfs-s3
  compose_data up -d --wait seaweedfs-s3
}

provision_seaweedfs_buckets() {
  local credentials_file="$VN_NEWS_SECRETS_HOST_DIR/storage-admin-s3-credentials"

  require_file "$credentials_file" "storage admin credentials"
  AWS_SHARED_CREDENTIALS_FILE="$credentials_file" \
    run_cicd_module scripts.services.seaweedfs.provision_buckets \
      --endpoint-url "$VN_NEWS_STORAGE_ENDPOINT_URL"
}

validate_seaweedfs() {
  curl -fsS http://127.0.0.1:9333/cluster/healthz >/dev/null
}

cleanup_seaweedfs() {
  return 0
}
