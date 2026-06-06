#!/usr/bin/env bash

bootstrap_event_bus() {
  (
    cd "$cicd_root"
    export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
    uv run python -m scripts.bootstrap_topics \
      --rpk-command "docker run --rm --entrypoint rpk ${REDPANDA_IMAGE:-redpandadata/redpanda:v26.1.9}" \
      --brokers "$VN_NEWS_REDPANDA_BOOTSTRAP_SERVERS" \
      --disable-auto-create
    uv run python -m scripts.register_event_schemas \
      --registry-url "$VN_NEWS_SCHEMA_REGISTRY_URL"
  )
}

bootstrap_storage() {
  local credentials_file="$VN_NEWS_SECRETS_HOST_DIR/storage-admin-s3-credentials"

  if [[ ! -f "$credentials_file" ]]; then
    echo "Missing storage admin credentials: $credentials_file" >&2
    exit 1
  fi

  (
    cd "$cicd_root"
    export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
    export AWS_SHARED_CREDENTIALS_FILE="$credentials_file"
    uv run python -m scripts.bootstrap_storage \
      --endpoint-url "$VN_NEWS_STORAGE_ENDPOINT_URL"
  )
}
