#!/usr/bin/env bash

deploy_ingestion_workers() {
  compose_processing pull article-fetcher article-extractor pipeline-metrics
  compose_processing up -d --wait article-fetcher article-extractor pipeline-metrics
}

provision_ingestion_workers() {
  return 0
}

validate_ingestion_workers() {
  return 0
}

cleanup_ingestion_workers() {
  return 0
}
