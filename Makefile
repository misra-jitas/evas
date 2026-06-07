# EVAS local development. Run `make help` for the target list.
PY := .venv/bin/python

.PHONY: help venv up down logs migrate buckets bootstrap api worker drain demo test verify fmt clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

venv: ## Create the virtualenv and install the package (+dev extras)
	python3 -m venv --system-site-packages .venv
	$(PY) -m pip install -q -e ".[dev]"

up: ## Start Postgres + MinIO
	docker compose up -d
	docker compose ps

down: ## Stop the stack (keeps data volumes)
	docker compose down

logs: ## Tail stack logs
	docker compose logs -f

migrate: ## Apply Alembic migrations to head
	$(PY) -m alembic upgrade head

buckets: ## Create the S3 buckets in MinIO
	$(PY) -m evas.cli create-buckets

bootstrap: up ## Bring up the stack, migrate, create buckets, seed a client + admin
	@echo "waiting for Postgres..."
	@until docker compose exec -T postgres pg_isready -U evas -d evas >/dev/null 2>&1; do sleep 1; done
	$(MAKE) migrate
	$(MAKE) buckets
	$(PY) -m evas.cli seed-client --name "Demo Co" --slug demo
	$(PY) -m evas.cli create-user --email admin@demo.co --full-name "Admin" --role admin
	@echo "Bootstrap complete. Start the API with 'make api' and the worker with 'make worker'."

api: ## Run the API (http://localhost:8000)
	$(PY) -m uvicorn evas.api.app:app --reload --port 8000

worker: ## Run the polling worker
	$(PY) -m evas.cli worker

drain: ## Process all queued jobs once
	$(PY) -m evas.cli drain

demo: ## Generate a test video, run it through the whole pipeline locally
	$(PY) -m evas.cli demo --slug demo

test: ## Run the test suite (needs the stack up)
	$(PY) -m pytest -q

verify: ## Lint + type-check + test
	ruff check .
	$(PY) -m mypy src
	$(PY) -m pytest -q

fmt: ## Format the code
	ruff format .
	ruff check --fix .

clean: ## Stop the stack and remove data volumes
	docker compose down -v
