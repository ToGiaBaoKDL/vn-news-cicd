#!/usr/bin/env bash

deploy_polaris() {
  local bootstrap_marker="/var/lib/postgresql/.vn-news-polaris-bootstrap-complete"

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

provision_polaris() {
  local credentials_file="$VN_NEWS_SECRETS_HOST_DIR/polaris-bootstrap-credentials.json"

  require_file "$credentials_file" "Polaris bootstrap credentials"
  run_cicd_module scripts.services.polaris.provision \
    --catalog-url "$VN_NEWS_POLARIS_CATALOG_URL" \
    --credentials-file "$credentials_file" \
    --storage-endpoint-url "$VN_NEWS_STORAGE_ENDPOINT_URL"
}

validate_polaris() {
  run_cicd_module scripts.services.polaris.validate \
    --catalog-url "$VN_NEWS_POLARIS_CATALOG_URL" \
    --storage-endpoint-url "$VN_NEWS_STORAGE_ENDPOINT_URL"
}
