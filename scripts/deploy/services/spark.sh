#!/usr/bin/env bash

deploy_spark_master() {
  compose_control pull spark-master
  compose_control up -d --wait spark-master
}

deploy_spark_worker() {
  compose_processing pull spark-worker
  compose_processing up -d --wait spark-worker
}

provision_spark() {
  return 0
}

spark_master_host() {
  local master_url="${VN_NEWS_SPARK_MASTER_URL:?set VN_NEWS_SPARK_MASTER_URL}"
  local host_port="${master_url#spark://}"

  printf '%s' "${host_port%%:*}"
}

validate_spark_master() {
  local master_host="${VN_NEWS_CONTROL_PRIVATE_IP:?set VN_NEWS_CONTROL_PRIVATE_IP}"
  local master_ui_port="${VN_NEWS_SPARK_MASTER_UI_PORT:?set VN_NEWS_SPARK_MASTER_UI_PORT}"

  run_cicd_module scripts.services.spark.validate_cluster master \
    --master-url "http://$master_host:$master_ui_port/json/"
}

validate_spark_worker_registered() {
  local master_host
  local master_ui_port="${VN_NEWS_SPARK_MASTER_UI_PORT:?set VN_NEWS_SPARK_MASTER_UI_PORT}"
  local max_attempts="${VN_NEWS_SPARK_WORKER_VALIDATION_ATTEMPTS:-12}"
  local sleep_seconds="${VN_NEWS_SPARK_WORKER_VALIDATION_SLEEP_SECONDS:-5}"
  local worker_host="${VN_NEWS_PROCESSING_PRIVATE_IP:?set VN_NEWS_PROCESSING_PRIVATE_IP}"

  master_host="$(spark_master_host)"
  run_cicd_module scripts.services.spark.validate_cluster worker \
    --master-url "http://$master_host:$master_ui_port/json/" \
    --worker-host "$worker_host" \
    --attempts "$max_attempts" \
    --sleep-seconds "$sleep_seconds"
}

cleanup_spark() {
  return 0
}
