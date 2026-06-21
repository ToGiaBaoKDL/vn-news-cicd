#!/usr/bin/env bash

deploy_seaweedfs() {
  compose_data pull seaweedfs-s3
  compose_data up -d --wait seaweedfs-s3
}

bootstrap_seaweedfs_buckets() {
  local credentials_file="$VN_NEWS_SECRETS_HOST_DIR/storage-admin-s3-credentials"

  if [[ ! -f "$credentials_file" ]]; then
    echo "Missing storage admin credentials: $credentials_file" >&2
    exit 1
  fi

  AWS_SHARED_CREDENTIALS_FILE="$credentials_file" \
    run_cicd_module scripts.services.seaweedfs.bootstrap_buckets \
      --endpoint-url "$VN_NEWS_STORAGE_ENDPOINT_URL"
}
