UV ?= uv
UV_CACHE_DIR ?= /tmp/uv-cache
IMAGE_MANIFEST ?=
SCHEMA_REGISTRY_ARGS ?=
SCHEMA_REGISTRY_PROVISION_ARGS ?=
STORAGE_PROVISION_ARGS ?=
TOPIC_PROVISION_ARGS ?=
RPK_COMMAND ?= docker compose --env-file ../vn-news-infra/env/data.env.example -f ../vn-news-infra/compose.data.yaml exec -T redpanda rpk

.PHONY: install lock validate lint format format-check test verify-images provision-ingestion provision-storage provision-schema-registry provision-topics register-event-schemas

install:
	$(UV) --cache-dir $(UV_CACHE_DIR) sync --all-groups

lock:
	$(UV) --cache-dir $(UV_CACHE_DIR) lock

validate:
	$(UV) --cache-dir $(UV_CACHE_DIR) run python -m scripts.workspace.verify

lint:
	$(UV) --cache-dir $(UV_CACHE_DIR) run ruff check .

format:
	$(UV) --cache-dir $(UV_CACHE_DIR) run ruff format .

format-check:
	$(UV) --cache-dir $(UV_CACHE_DIR) run ruff format --check .

test:
	$(UV) --cache-dir $(UV_CACHE_DIR) run python -m pytest

verify-images:
	$(UV) --cache-dir $(UV_CACHE_DIR) run python -m scripts.images.verify --manifest '$(IMAGE_MANIFEST)'

provision-ingestion: provision-schema-registry provision-topics register-event-schemas provision-storage

provision-storage:
	$(UV) --cache-dir $(UV_CACHE_DIR) run python -m scripts.services.seaweedfs.provision_buckets $(STORAGE_PROVISION_ARGS)

provision-schema-registry:
	$(UV) --cache-dir $(UV_CACHE_DIR) run python -m scripts.services.redpanda.provision_schema_registry --rpk-command "$(RPK_COMMAND)" --brokers redpanda:9092 $(SCHEMA_REGISTRY_PROVISION_ARGS)

provision-topics:
	$(UV) --cache-dir $(UV_CACHE_DIR) run python -m scripts.services.redpanda.provision_topics --rpk-command "$(RPK_COMMAND)" --brokers redpanda:9092 $(TOPIC_PROVISION_ARGS)

register-event-schemas:
	$(UV) --cache-dir $(UV_CACHE_DIR) run python -m scripts.services.redpanda.register_schemas $(SCHEMA_REGISTRY_ARGS)
