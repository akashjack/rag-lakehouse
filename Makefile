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

lake-up: ## Start lakehouse stack (minio + iceberg-rest + spark)
	docker network create ragnet 2>/dev/null || true
	docker compose -f infra/docker/docker-compose.minio.yml --env-file .env up -d
	docker compose -f infra/docker/docker-compose.lakehouse.yml --env-file .env up -d

lake-down: ## Stop lakehouse stack
	docker compose -f infra/docker/docker-compose.lakehouse.yml down
	docker compose -f infra/docker/docker-compose.minio.yml down

lake-etl: ## Run bronze->silver->gold ETL via spark-submit
	docker exec -e PYTHONPATH=/opt/lakehouse -e ICEBERG_REST_URI=http://iceberg-rest:8181 -e S3_ENDPOINT=http://minio:9000 -e AWS_ACCESS_KEY_ID=minioadmin -e AWS_SECRET_ACCESS_KEY=minioadmin rag-spark /opt/spark/bin/spark-submit /opt/lakehouse/lakehouse/jobs/bronze_to_silver.py
	docker exec -e PYTHONPATH=/opt/lakehouse -e ICEBERG_REST_URI=http://iceberg-rest:8181 -e S3_ENDPOINT=http://minio:9000 -e AWS_ACCESS_KEY_ID=minioadmin -e AWS_SECRET_ACCESS_KEY=minioadmin rag-spark /opt/spark/bin/spark-submit /opt/lakehouse/lakehouse/jobs/silver_to_gold.py

lake-demo-tt: ## Demo Iceberg time travel
	docker exec -e PYTHONPATH=/opt/lakehouse -e ICEBERG_REST_URI=http://iceberg-rest:8181 -e S3_ENDPOINT=http://minio:9000 -e AWS_ACCESS_KEY_ID=minioadmin -e AWS_SECRET_ACCESS_KEY=minioadmin rag-spark /opt/spark/bin/spark-submit /opt/lakehouse/scripts/demo_time_travel.py

lake-demo-evo: ## Demo Iceberg schema evolution
	docker exec -e PYTHONPATH=/opt/lakehouse -e ICEBERG_REST_URI=http://iceberg-rest:8181 -e S3_ENDPOINT=http://minio:9000 -e AWS_ACCESS_KEY_ID=minioadmin -e AWS_SECRET_ACCESS_KEY=minioadmin rag-spark /opt/spark/bin/spark-submit /opt/lakehouse/scripts/demo_schema_evolution.py
