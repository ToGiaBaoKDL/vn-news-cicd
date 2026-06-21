#!/usr/bin/env bash

deploy_polaris() {
  local bootstrap_marker="/var/lib/postgresql/data/.vn-news-polaris-bootstrap-complete"

  compose_data pull polaris-db polaris
  compose_data --profile bootstrap pull polaris-bootstrap
  compose_data up -d --wait polaris-db
  if compose_data exec -T polaris-db test -f "$bootstrap_marker"; then
    echo "Polaris bootstrap marker exists; skipping bootstrap"
  else
    compose_data --profile bootstrap run --rm polaris-bootstrap
    compose_data exec -T polaris-db touch "$bootstrap_marker"
  fi
  compose_data up -d --wait polaris
}

bootstrap_polaris_catalog() {
  local credentials_file="$VN_NEWS_SECRETS_HOST_DIR/polaris-bootstrap-credentials.json"

  if [[ ! -f "$credentials_file" ]]; then
    echo "Missing Polaris bootstrap credentials: $credentials_file" >&2
    exit 1
  fi
  run_cicd_module scripts.services.polaris.bootstrap_catalog \
    --catalog-url "$VN_NEWS_POLARIS_CATALOG_URL" \
    --credentials-file "$credentials_file" \
    --storage-endpoint-url "$VN_NEWS_STORAGE_ENDPOINT_URL"
}

provision_polaris_access() (
  local credentials_file="$VN_NEWS_SECRETS_HOST_DIR/polaris-bootstrap-credentials.json"
  local runtime_credentials_current_file runtime_credentials_output_file runtime_secret_content_name tmp_dir
  local rotate_args=()

  if [[ ! -f "$credentials_file" ]]; then
    echo "Missing Polaris bootstrap credentials: $credentials_file" >&2
    exit 1
  fi
  : "${VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID:?set VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID}"

  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' EXIT
  runtime_credentials_current_file="$tmp_dir/polaris-client-credentials.current.json"
  runtime_credentials_output_file="$tmp_dir/polaris-client-credentials.new.json"
  read_vault_secret_to_file \
    VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID \
    "$runtime_credentials_current_file"
  if [[ "${VN_NEWS_POLARIS_ROTATE_RUNTIME_CREDENTIALS:-false}" =~ ^(1|true|yes|on)$ ]]; then
    rotate_args=(--rotate-runtime-credentials)
  fi

  run_cicd_module scripts.services.polaris.provision_access \
    --catalog-url "$VN_NEWS_POLARIS_CATALOG_URL" \
    --credentials-file "$credentials_file" \
    --storage-endpoint-url "$VN_NEWS_STORAGE_ENDPOINT_URL" \
    --runtime-credentials-output-file "$runtime_credentials_output_file" \
    --current-runtime-credentials-file "$runtime_credentials_current_file" \
    "${rotate_args[@]}"
  if [[ -s "$runtime_credentials_output_file" ]]; then
    runtime_secret_content_name="polaris-runtime-$(date -u +%Y%m%dT%H%M%SZ)"
    update_vault_secret_from_file \
      VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID \
      "$runtime_credentials_output_file" \
      "$runtime_secret_content_name"
    echo "updated Polaris runtime client credentials in OCI Vault"
  fi
)

validate_polaris_access() (
  local runtime_credentials_file tmp_dir

  : "${VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID:?set VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID}"
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' EXIT
  runtime_credentials_file="$tmp_dir/polaris-client-credentials.json"
  read_vault_secret_to_file \
    VN_NEWS_POLARIS_CLIENT_CREDENTIALS_SECRET_OCID \
    "$runtime_credentials_file"
  run_cicd_module scripts.services.polaris.validate_access \
    --catalog-url "$VN_NEWS_POLARIS_CATALOG_URL" \
    --storage-endpoint-url "$VN_NEWS_STORAGE_ENDPOINT_URL" \
    --runtime-credentials-file "$runtime_credentials_file"
)
