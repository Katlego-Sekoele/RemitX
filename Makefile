# Shortcuts for the project's everyday commands. `make` lists them.
#
# Python recipes use each package's own virtualenv (api/.venv,
# tools/seeder/.venv), so nothing needs activating first; `make api-install`
# and `make seeder-install` create them.

.DEFAULT_GOAL := help
SHELL := bash

DEV_COMPOSE := docker compose -f docker-compose.dev.yml
LOADTEST_COMPOSE := docker compose -f tools/loadtest/docker-compose.yml --profile tools

.PHONY: help
help: ## List the targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-18s %s\n", $$1, $$2} /^##@ / {printf "\n%s\n", substr($$0, 5)}' $(MAKEFILE_LIST)

##@ Dev stack (docker-compose.dev.yml)

.PHONY: up down
up: ## Start API, worker, frontend, Postgres, Redis and MinIO (foreground logs)
	$(DEV_COMPOSE) up --build

down: ## Stop the dev stack
	$(DEV_COMPOSE) down

##@ API

.PHONY: api-install api-dev api-test api-lint api-migrate openapi
api-install: ## Create api/.venv and install the API with its dev tools
	cd api && python3.11 -m venv .venv && .venv/bin/pip install -e '.[dev]'

api-dev: ## Run the API dev server on port 4200 (PORT)
	cd api && .venv/bin/python -m remitx_api

api-test: ## Run the API tests
	cd api && .venv/bin/pytest

api-lint: ## Fix and format the API with ruff
	cd api && .venv/bin/ruff check --fix . && .venv/bin/ruff format .

api-migrate: ## Apply database migrations to the DATABASE_URL database
	cd api && .venv/bin/alembic upgrade head

openapi: ## Regenerate frontend/openapi.json from the API's routes
	cd api && .venv/bin/python scripts/export_openapi.py

##@ Frontend

.PHONY: frontend-install frontend-dev frontend-lint frontend-test
frontend-install: ## Install the frontend's dependencies
	cd frontend && npm ci

frontend-dev: ## Run the Vite dev server on 5173
	cd frontend && npm run dev

frontend-lint: ## Typecheck and check formatting
	cd frontend && npm run lint

frontend-test: ## Run the frontend unit tests
	cd frontend && npm test

##@ Seeder (local only)

.PHONY: seeder-install seeder seeder-test
seeder-install: ## Create tools/seeder/.venv with the API and the seeder
	cd tools/seeder && python3.11 -m venv .venv && .venv/bin/pip install -e ../../api -e '.[dev]'

seeder: ## Open the seeder UI on http://127.0.0.1:8090
	cd tools/seeder && .venv/bin/python -m remitx_seeder

seeder-test: ## Run the seeder tests (needs SEEDER_TEST_DATABASE_URL)
	cd tools/seeder && .venv/bin/pytest

##@ Load test (tools/loadtest)

.PHONY: loadtest loadtest-down loadtest-canvas
loadtest: ## Load-test the API (LOADTEST_PROFILE=default); report in tools/loadtest/results/
	tools/loadtest/run.sh

loadtest-down: ## Delete the load-test stack after an interrupted or KEEP_STACK=1 run
	$(LOADTEST_COMPOSE) down --volumes --remove-orphans

loadtest-canvas: ## Rebuild summary + canvas + HTML (RESULTS=tools/loadtest/results/<ts>)
	@test -n "$(RESULTS)" || (echo "Set RESULTS=tools/loadtest/results/<timestamp>" >&2; exit 1)
	@if [ -x tools/seeder/.venv/bin/python ]; then \
	  tools/seeder/.venv/bin/python tools/loadtest/to_canvas.py "$(RESULTS)"; \
	else \
	  PYTHONPATH=tools/seeder python3 tools/loadtest/to_canvas.py "$(RESULTS)"; \
	fi

##@ Git hooks

.PHONY: hooks
hooks: ## Install the pre-commit hooks
	./scripts/setup-hooks.sh
