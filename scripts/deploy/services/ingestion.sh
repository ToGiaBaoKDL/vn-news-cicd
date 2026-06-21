#!/usr/bin/env bash

deploy_ingestion_workers() {
  compose_processing pull article-fetcher article-extractor pipeline-metrics
  compose_processing up -d --wait article-fetcher article-extractor pipeline-metrics
}
