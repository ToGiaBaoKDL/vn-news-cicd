#!/usr/bin/env bash

deploy_redpanda() {
  compose_data pull redpanda redpanda-console
  compose_data up -d --wait redpanda redpanda-console
}

deploy_seaweedfs() {
  compose_data pull seaweedfs-s3
  compose_data up -d --wait seaweedfs-s3
}

deploy_airflow() {
  compose_control pull airflow-db docker-socket-proxy airflow-scheduler airflow-dag-processor airflow-api-server
  compose_control up -d --wait airflow-db
  compose_control --profile bootstrap run --rm airflow-bootstrap
  compose_control up -d --wait docker-socket-proxy airflow-scheduler airflow-dag-processor airflow-api-server
}

deploy_app() {
  local app_root="$repos_root/vn-news-app"

  docker compose --env-file "$env_file" -f "$app_root/compose.yaml" pull
  docker compose --env-file "$env_file" -f "$app_root/compose.yaml" up -d --wait
}

deploy_workers() {
  compose_processing pull
  compose_processing up -d --wait
}
