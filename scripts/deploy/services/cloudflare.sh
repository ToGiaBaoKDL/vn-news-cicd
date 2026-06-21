#!/usr/bin/env bash

deploy_data_access() {
  compose_data pull cloudflared-data
  compose_data up -d --wait cloudflared-data
}

deploy_control_access() {
  compose_control pull cloudflared-control
  compose_control up -d --wait cloudflared-control
}
