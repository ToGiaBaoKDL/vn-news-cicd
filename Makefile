UV ?= uv
UV_CACHE_DIR ?= /tmp/uv-cache
BUILD_IMAGE_ARGS ?=
TAG ?= dev
SCHEMA_REGISTRY_ARGS ?=
STORAGE_BOOTSTRAP_ARGS ?=
TOPIC_BOOTSTRAP_ARGS ?=
RPK_COMMAND ?= docker compose -f ../vn-news-infra/compose.yaml exec -T redpanda rpk

.PHONY: install lock validate lint format format-check test build-images push-images bootstrap-ingestion bootstrap-storage bootstrap-topics register-event-schemas

install:
	$(UV) --cache-dir $(UV_CACHE_DIR) sync --all-groups

lock:
	$(UV) --cache-dir $(UV_CACHE_DIR) lock

validate:
	$(UV) --cache-dir $(UV_CACHE_DIR) run python -m scripts.validate_workspace

lint:
	$(UV) --cache-dir $(UV_CACHE_DIR) run ruff check .

format:
	$(UV) --cache-dir $(UV_CACHE_DIR) run ruff format .

format-check:
	$(UV) --cache-dir $(UV_CACHE_DIR) run ruff format --check .

test:
	$(UV) --cache-dir $(UV_CACHE_DIR) run python -m pytest

build-images:
	$(UV) --cache-dir $(UV_CACHE_DIR) run python -m scripts.build_images --tag $(TAG) $(BUILD_IMAGE_ARGS)

push-images:
	$(UV) --cache-dir $(UV_CACHE_DIR) run python -m scripts.build_images --tag $(TAG) --push $(BUILD_IMAGE_ARGS)

bootstrap-ingestion: bootstrap-topics register-event-schemas bootstrap-storage

bootstrap-storage:
	$(UV) --cache-dir $(UV_CACHE_DIR) run python scripts/bootstrap_storage.py $(STORAGE_BOOTSTRAP_ARGS)

bootstrap-topics:
	$(UV) --cache-dir $(UV_CACHE_DIR) run python scripts/bootstrap_topics.py --rpk-command "$(RPK_COMMAND)" --brokers redpanda:9092 $(TOPIC_BOOTSTRAP_ARGS)

register-event-schemas:
	$(UV) --cache-dir $(UV_CACHE_DIR) run python scripts/register_event_schemas.py $(SCHEMA_REGISTRY_ARGS)
