#!/usr/bin/env bash

deploy_redpanda() {
  compose_data pull redpanda redpanda-console
  compose_data up -d --wait redpanda redpanda-console
  compose_data exec -T redpanda rpk cluster config set auto_create_topics_enabled false --no-confirm
}

bootstrap_redpanda_topics() {
  run_cicd_module scripts.services.redpanda.bootstrap_topics \
    --rpk-command "docker run --rm --entrypoint rpk ${REDPANDA_IMAGE:-redpandadata/redpanda:v26.1.9}" \
    --brokers "$VN_NEWS_REDPANDA_BOOTSTRAP_SERVERS"
}

bootstrap_redpanda_schemas() {
  run_cicd_module scripts.services.redpanda.register_schemas \
    --registry-url "$VN_NEWS_SCHEMA_REGISTRY_URL"
}
