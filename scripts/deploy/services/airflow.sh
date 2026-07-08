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
  local expected_dag="${VN_NEWS_AIRFLOW_EXPECTED_DAG_ID:?set VN_NEWS_AIRFLOW_EXPECTED_DAG_ID}"
  local max_attempts="${VN_NEWS_AIRFLOW_DAG_VALIDATION_ATTEMPTS:-12}"
  local sleep_seconds="${VN_NEWS_AIRFLOW_DAG_VALIDATION_SLEEP_SECONDS:-10}"

  compose_control exec -T airflow-api-server \
    curl -fsS http://localhost:8080/api/v2/monitor/health >/dev/null

  for _ in $(seq 1 "$max_attempts"); do
    if compose_control exec -T airflow-api-server airflow dags list --output json \
      | run_cicd_module scripts.services.airflow.validate_dag --expected-dag "$expected_dag"; then
      echo "validated Airflow DAG: $expected_dag"
      return
    fi
    sleep "$sleep_seconds"
  done

  echo "Airflow DAG not found after deploy: $expected_dag" >&2
  compose_control exec -T airflow-api-server airflow dags list >&2
  exit 1
}

cleanup_airflow() {
  return 0
}
