#!/usr/bin/env bash

deploy_spark_master() {
  compose_control pull spark-master
  compose_control up -d --wait spark-master
}

deploy_spark_worker() {
  compose_processing pull spark-worker
  compose_processing up -d --wait spark-worker
}

spark_master_host() {
  local master_url="${VN_NEWS_SPARK_MASTER_URL:?set VN_NEWS_SPARK_MASTER_URL}"
  local host_port="${master_url#spark://}"

  printf '%s' "${host_port%%:*}"
}

validate_spark_master() {
  local master_host="${VN_NEWS_CONTROL_PRIVATE_IP:?set VN_NEWS_CONTROL_PRIVATE_IP}"
  local master_ui_port="${VN_NEWS_SPARK_MASTER_UI_PORT:?set VN_NEWS_SPARK_MASTER_UI_PORT}"

  curl -fsS "http://$master_host:$master_ui_port/json/" | python3 -m json.tool >/dev/null
  echo "validated Spark master: $master_host:$master_ui_port"
}

validate_spark_worker_registered() {
  local master_host
  local master_ui_port="${VN_NEWS_SPARK_MASTER_UI_PORT:?set VN_NEWS_SPARK_MASTER_UI_PORT}"
  local max_attempts="${VN_NEWS_SPARK_WORKER_VALIDATION_ATTEMPTS:-12}"
  local sleep_seconds="${VN_NEWS_SPARK_WORKER_VALIDATION_SLEEP_SECONDS:-5}"
  local worker_host="${VN_NEWS_PROCESSING_PRIVATE_IP:?set VN_NEWS_PROCESSING_PRIVATE_IP}"

  master_host="$(spark_master_host)"
  for _ in $(seq 1 "$max_attempts"); do
    if curl -fsS "http://$master_host:$master_ui_port/json/" | python3 -c '
import json
import sys

worker_host = sys.argv[1]
workers = json.load(sys.stdin).get("workers", [])
raise SystemExit(not any(
    worker.get("host") == worker_host and worker.get("state") == "ALIVE"
    for worker in workers
    if isinstance(worker, dict)
))
' "$worker_host"; then
      echo "validated Spark worker registration: $worker_host -> $master_host:$master_ui_port"
      return
    fi
    sleep "$sleep_seconds"
  done

  echo "Spark worker is not registered as ALIVE on master: $worker_host" >&2
  exit 1
}
