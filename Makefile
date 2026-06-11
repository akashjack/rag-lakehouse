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

# ===== Phase 3: indexer (Oracle 23ai + Ollama in Docker) =====
.PHONY: idx-up idx-down idx-pull-model idx-oracle-shell idx-status idx-ollama-check

# Local in-container Ollama: hostname inside ragnet is 'ollama:11434'.
# From the host, it's localhost:11434 (via port publish).
OLLAMA_BASE_URL_HOST ?= http://localhost:11434
OLLAMA_EMBED_MODEL ?= nomic-embed-text

idx-up:
	docker compose -f infra/docker/docker-compose.indexer.yml up -d
	@echo ""
	@echo "Oracle 23ai is starting (first boot takes 60-120s)..."
	@echo "Watch progress with: docker logs -f rag-oracle"
	@echo "Ready when you see: DATABASE IS READY TO USE!"
	@echo ""
	@echo "Then run: make idx-pull-model"

idx-down:
	docker compose -f infra/docker/docker-compose.indexer.yml down

idx-pull-model:
	docker exec rag-ollama ollama pull $(OLLAMA_EMBED_MODEL)
	@echo ""
	@echo "Model pulled. Smoke test:"
	@$(MAKE) -s idx-ollama-check

idx-ollama-check:
	@echo "=== Ollama @ $(OLLAMA_BASE_URL_HOST) ==="
	@curl -fsS $(OLLAMA_BASE_URL_HOST)/api/tags > /tmp/.ollama_tags.json || \
		(echo "FAILED: cannot reach $(OLLAMA_BASE_URL_HOST). Is the container up? Check 'docker ps | grep rag-ollama'."; exit 1)
	@python3 -c "import json; d=json.load(open('/tmp/.ollama_tags.json')); models=[m['name'] for m in d.get('models',[])]; print('models:', models); assert any('$(OLLAMA_EMBED_MODEL)' in m for m in models), '$(OLLAMA_EMBED_MODEL) not pulled — run: make idx-pull-model'"
	@echo ""
	@echo "=== Embedding smoke test ==="
	@curl -fsS $(OLLAMA_BASE_URL_HOST)/api/embed \
		-d '{"model":"$(OLLAMA_EMBED_MODEL)","input":"hello world"}' \
		| python3 -c "import sys, json; d=json.load(sys.stdin); print(f'embedding dim: {len(d[\"embeddings\"][0])}')"

idx-oracle-shell:
	docker exec -it rag-oracle sqlplus sys/$${ORACLE_PWD:-RagPass_2026}@FREEPDB1 as sysdba

idx-status:
	@echo "=== Oracle ==="
	@docker exec rag-oracle bash -c 'echo "SELECT name, open_mode FROM v\$$pdbs;" | sqlplus -s sys/$${ORACLE_PWD:-RagPass_2026}@FREEPDB1 as sysdba' 2>&1 | grep -E "NAME|FREEPDB1|ORA-" | head -3 || echo "Oracle not reachable"
	@echo ""
	@$(MAKE) -s idx-ollama-check

idx-bootstrap-user:
	docker cp services/indexer/sql/bootstrap_user.sql rag-oracle:/tmp/bootstrap_user.sql
	docker exec rag-oracle bash -c 'sqlplus -s sys/$${ORACLE_PWD:-RagPass_2026}@FREEPDB1 as sysdba @/tmp/bootstrap_user.sql'


# ===== Phase 3: indexer CLI shortcuts =====
.PHONY: idx-schema-init idx-stats idx-search

idx-schema-init:
	cd services/indexer && .venv/bin/python -m indexer schema-init

idx-stats:
	cd services/indexer && .venv/bin/python -m indexer stats

# Usage: make idx-search Q="what is a kubernetes pod?"
idx-search:
	@cd services/indexer && .venv/bin/python -m indexer search "$(Q)" --k $${K:-5}
