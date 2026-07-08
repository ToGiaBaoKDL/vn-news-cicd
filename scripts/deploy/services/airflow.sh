#!/usr/bin/env bash

deploy_airflow() {
  compose_control pull airflow-db docker-socket-proxy airflow-scheduler airflow-dag-processor airflow-api-server
  compose_control up -d --wait airflow-db
  compose_control --profile bootstrap run --rm airflow-bootstrap
  compose_control up -d --wait docker-socket-proxy airflow-scheduler airflow-dag-processor airflow-api-server
}

provision_airflow() {
  return 0
}

validate_airflow() {
  compose_control exec -T airflow-api-server \
    curl -fsS http://localhost:8080/api/v2/monitor/health >/dev/null
}

cleanup_airflow() {
  return 0
}
