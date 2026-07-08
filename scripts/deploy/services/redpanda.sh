#!/usr/bin/env bash

deploy_redpanda() {
  compose_data pull redpanda redpanda-console
  compose_data up -d --wait redpanda redpanda-console
}

provision_redpanda_topics() {
  local rpk_command

  rpk_command="docker compose --env-file $env_file -f $infra_root/compose.data.yaml exec -T redpanda rpk"
  run_cicd_module scripts.services.redpanda.provision_topics \
    --rpk-command "$rpk_command" \
    --brokers localhost:9092 \
    --disable-auto-create
}

provision_redpanda_schemas() {
  run_cicd_module scripts.services.redpanda.register_schemas \
    --registry-url "$VN_NEWS_SCHEMA_REGISTRY_URL"
}

validate_redpanda() {
  compose_data exec -T redpanda rpk cluster health -X brokers=localhost:9092
}

cleanup_redpanda() {
  return 0
}
