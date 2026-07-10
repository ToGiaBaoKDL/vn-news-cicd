#!/usr/bin/env bash

deploy_ingestion_workers() {
  compose_processing pull article-fetcher article-extractor
  compose_processing up -d --wait --remove-orphans article-fetcher article-extractor
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
