.PHONY: help setup fmt lint test up down clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Install pre-commit + uv + base deps
	pip install uv pre-commit
	pre-commit install
	@echo "Run 'cp .env.example .env' and edit secrets"

fmt: ## Format code
	uv run ruff format .

lint: ## Lint code
	uv run ruff check . --fix
	uv run mypy services/

test: ## Run tests
	uv run pytest

up: ## Start full stack
	docker compose --env-file .env up -d

down: ## Stop stack
	docker compose down

logs: ## Tail logs
	docker compose logs -f

clean: ## Nuke containers + volumes
	docker compose down -v
	rm -rf volumes/ spark-warehouse/ metastore_db/

typecheck: ## Run mypy type checking
	cd services/ingestion && uv run mypy ingestion/

# Usage: make idx-search-hybrid Q="what is a kubernetes service?"
idx-search-hybrid:
	@cd services/indexer && .venv/bin/python -m indexer search "$(Q)" --k ${K:-5} --hybrid

# ===== Phase 9: observability =====
.PHONY: obs-up obs-down

obs-up:
	docker compose -f infra/docker/docker-compose.observability.yml up -d
	@echo 'Prometheus: http://localhost:9090'
	@echo 'Grafana:    http://localhost:3000  (admin/admin)'

obs-down:
	docker compose -f infra/docker/docker-compose.observability.yml down

# ===== Phase 10: RAGAS-style evaluation =====
.PHONY: eval-rag

eval-rag:
	cd services/indexer && .venv/bin/python ../../scripts/eval_rag.py

# ===== Phase 12: corpus expansion =====
.PHONY: corpus-expand

corpus-expand:
	cd services/indexer && .venv/bin/python ../../scripts/expand_corpus.py
