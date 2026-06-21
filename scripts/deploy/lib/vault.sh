#!/usr/bin/env bash

vault_oci_command() {
  local auth_args=()

  if [[ "${VN_NEWS_OCI_AUTH:-instance_principal}" != "default" ]]; then
    auth_args=(--auth "${VN_NEWS_OCI_AUTH:-instance_principal}")
  fi
  "${OCI_BIN:-oci}" "$@" "${auth_args[@]}"
}

read_vault_secret_to_file() {
  local env_name="$1"
  local target_file="$2"
  local secret_id="${!env_name:-}"

  if [[ -z "$secret_id" ]]; then
    echo "Missing required environment variable: $env_name" >&2
    exit 1
  fi

  vault_oci_command secrets secret-bundle get \
    --secret-id "$secret_id" \
    --query 'data."secret-bundle-content".content' \
    --raw-output \
    | base64 --decode >"$target_file"
}

update_vault_secret_from_file() {
  local env_name="$1"
  local source_file="$2"
  local content_name="$3"
  local secret_id="${!env_name:-}"
  local encoded

  if [[ -z "$secret_id" ]]; then
    echo "Missing required environment variable: $env_name" >&2
    exit 1
  fi

  encoded="$(base64 -w 0 "$source_file")"
  vault_oci_command vault secret update-base64 \
    --secret-id "$secret_id" \
    --secret-content-content "$encoded" \
    --secret-content-stage CURRENT \
    --secret-content-name "$content_name" \
    --force \
    --wait-for-state ACTIVE >/dev/null
}
