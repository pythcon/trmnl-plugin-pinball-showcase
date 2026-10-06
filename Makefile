# Common tasks. API tasks need uv; plugin tasks need Docker (or the trmnl_preview gem).
.DEFAULT_GOAL := help
TRMNLP := docker run --rm -e CI=true -v "$(CURDIR)/plugin":/plugin trmnl/trmnlp:latest

.PHONY: help
help: ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---- API -------------------------------------------------------------------------------
.PHONY: api-dev api-test api-lint api-format
api-dev: ## Run the API locally with reload on :8080
	cd api && uv run uvicorn pinball_showcase.main:app --reload --port 8080

api-test: ## Run API tests
	cd api && uv run pytest

api-lint: ## Lint and format-check the API
	cd api && uv run ruff check . && uv run ruff format --check .

api-format: ## Format the API code
	cd api && uv run ruff format . && uv run ruff check --fix .

# ---- Container -------------------------------------------------------------------------
.PHONY: image up down logs
image: ## Build the API container image
	docker build -t ghcr.io/pythcon/trmnl-plugin-pinball-showcase:dev api

up: ## Self-host: start the API with docker compose
	docker compose up -d --build

down: ## Stop the compose stack
	docker compose down

logs: ## Tail API logs
	docker compose logs -f api

# ---- Plugin ----------------------------------------------------------------------------
.PHONY: fixtures preview plugin-lint plugin-test plugin-serve plugin-push
fixtures: ## Regenerate plugin test fixtures from the live OPDB export
	cd api && uv run python scripts/refresh_fixtures.py

plugin-lint: ## trmnlp lint (TRMNL best practices)
	$(TRMNLP) lint

plugin-test: ## Render every view on OG/X/BWRY; report in plugin/report/index.html
	$(TRMNLP) test --report report

preview: ## Local virtual TRMNL at http://localhost:4567, backed by the API on this machine
	docker compose up -d --build api
	@echo "Waiting for the API to load the OPDB export..."
	@until curl -fsS localhost:$${PINBALL_PORT:-8080}/readyz >/dev/null 2>&1; do sleep 1; done
	@echo "Open http://localhost:4567  (Ctrl-C to stop the viewer; 'make down' stops the API)"
	cd plugin && PINBALL_API_URL=http://host.docker.internal:$${PINBALL_PORT:-8080} bin/trmnlp serve

plugin-serve: ## Live preview at http://localhost:4567 (polls the hosted API)
	cd plugin && bin/trmnlp serve

plugin-push: ## Upload the plugin to your TRMNL account (needs trmnlp login or TRMNL_API_KEY)
	cd plugin && bin/trmnlp push

.PHONY: check
check: api-lint api-test plugin-lint plugin-test ## Everything CI runs
