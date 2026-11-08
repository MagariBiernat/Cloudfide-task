# Taskly — local workflow.
#   Docker targets (up, test, coverage, ...) need Docker Engine / Docker Desktop.
#   *-local targets run tests directly on the host (python3.12-venv + Node >= 22.12).

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE    := docker compose
UID_GID    := $(shell id -u):$(shell id -g)
PY_IMAGE   := python:3.12-slim
NODE_IMAGE := node:22-alpine
VENV       := backend/.venv
# Host venv uses the CI interpreter (3.12): on 3.14 the existing tests break (create_autospec + lazy annotations).
PYTHON     ?= $(shell command -v python3.12 2>/dev/null || uv python find 3.12 2>/dev/null || echo python3)
VENV_PY    := $(CURDIR)/$(VENV)/bin/python

# Named volumes cache dependencies between runs (fast + no root-owned node_modules on host).
BACKEND_RUN  := docker run --rm -t \
	-v "$(CURDIR)/backend:/src" -w /src \
	-v taskly-pip-cache:/root/.cache/pip \
	-e PYTHONDONTWRITEBYTECODE=1 \
	$(PY_IMAGE)
FRONTEND_RUN := docker run --rm -t \
	-v "$(CURDIR)/frontend:/src" -w /src \
	-v taskly-node-modules:/src/node_modules \
	-v taskly-npm-cache:/root/.npm \
	$(NODE_IMAGE)

.PHONY: help env check-docker up down restart logs ps clean \
	test test-backend test-frontend coverage coverage-backend coverage-frontend storybook \
	install-local test-local test-backend-local test-frontend-local \
	coverage-local coverage-backend-local coverage-frontend-local clean-local \
	pipeline pipeline-prepare pipeline-agent pipeline-verify pipeline-report backfill \
	test-agent-scripts

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from .env.example if missing
	@test -f .env || (install -m 600 .env.example .env && echo "Created .env from .env.example (chmod 600)")

check-docker: ## Verify Docker CLI + daemon + compose plugin are available
	@command -v docker >/dev/null 2>&1 || { \
		echo "ERROR: 'docker' not found in PATH."; \
		echo "  Option A (WSL): install Docker Desktop for Windows and enable"; \
		echo "     Settings -> Resources -> WSL integration -> <your distro>."; \
		echo "  Option B (WSL/Ubuntu native):"; \
		echo "     curl -fsSL https://get.docker.com | sudo sh"; \
		echo "     sudo usermod -aG docker \$$USER && newgrp docker"; \
		echo "  Without Docker you can still run tests: make install-local && make test-local"; \
		exit 1; }
	@docker info >/dev/null 2>&1 || { \
		echo "ERROR: Docker daemon not reachable. Start Docker Desktop or 'sudo systemctl start docker'."; \
		echo "  (Permission denied? -> sudo usermod -aG docker \$$USER, then re-login.)"; \
		exit 1; }
	@docker compose version >/dev/null 2>&1 || { \
		echo "ERROR: 'docker compose' plugin missing. Install docker-compose-plugin."; exit 1; }

# --- Application stack (Docker) ----------------------------------------------

up: check-docker env ## Build and start postgres + backend + frontend (waits for healthchecks)
	$(COMPOSE) up --build -d --wait
	@echo ""
	@echo "  App:      http://localhost:8080"
	@echo "  API docs: http://localhost:8000/docs"

down: check-docker ## Stop the stack (keeps DB volume)
	$(COMPOSE) down

restart: down up ## Restart the stack

logs: check-docker ## Follow logs of all services
	$(COMPOSE) logs -f

ps: check-docker ## Show service status
	$(COMPOSE) ps

clean: check-docker ## Stop the stack and remove DB volume + dependency caches
	$(COMPOSE) down -v
	-docker volume rm taskly-node-modules taskly-npm-cache taskly-pip-cache

# --- Tests in containers (unit tests do not need the database) ---------------

test: test-backend test-frontend ## [docker] Run backend and frontend unit tests

test-backend: check-docker ## [docker] Backend tests (pytest)
	$(BACKEND_RUN) sh -c "pip install -q -r requirements.txt && python -m pytest; s=\$$?; chown -R $(UID_GID) /src; exit \$$s"

test-frontend: check-docker ## [docker] Frontend tests (vitest)
	$(FRONTEND_RUN) sh -c "npm ci --no-audit --no-fund --loglevel=error && npm test; s=\$$?; chown -R $(UID_GID) /src/coverage 2>/dev/null; exit \$$s"

coverage: coverage-backend coverage-frontend ## [docker] Coverage for both sides

coverage-backend: check-docker ## [docker] Backend coverage -> backend/coverage/html/index.html
	$(BACKEND_RUN) sh -c "pip install -q -r requirements.txt && python -m pytest --cov=app --cov-report=term-missing --cov-report=html --cov-report=xml --cov-report=json; s=\$$?; chown -R $(UID_GID) /src; exit \$$s"

coverage-frontend: check-docker ## [docker] Frontend coverage -> frontend/coverage/index.html
	$(FRONTEND_RUN) sh -c "npm ci --no-audit --no-fund --loglevel=error && npm run test:coverage; s=\$$?; chown -R $(UID_GID) /src/coverage 2>/dev/null; exit \$$s"

storybook: check-docker ## [docker] Storybook -> http://localhost:6006
	docker run --rm -it -p 127.0.0.1:6006:6006 \
		-v "$(CURDIR)/frontend:/src" -w /src \
		-v taskly-node-modules:/src/node_modules \
		-v taskly-npm-cache:/root/.npm \
		$(NODE_IMAGE) sh -c "npm ci --no-audit --no-fund --loglevel=error && npx storybook dev -p 6006 --host 0.0.0.0 --no-open"

# --- Tests on the host (no Docker) --------------------------------------------

$(VENV_PY):
	@$(PYTHON) -c "import ensurepip" 2>/dev/null || { \
		echo "ERROR: python venv support missing. Run: sudo apt install python3.12-venv"; exit 1; }
	$(PYTHON) -m venv $(VENV)
	$(VENV_PY) -m pip install -q --upgrade pip
	$(VENV_PY) -m pip install -q -r backend/requirements.txt

frontend/node_modules: frontend/package-lock.json
	@command -v npm >/dev/null 2>&1 || { echo "ERROR: npm not found (need Node >= 22.12)."; exit 1; }
	cd frontend && npm ci --no-audit --no-fund
	@touch frontend/node_modules

install-local: $(VENV_PY) frontend/node_modules ## [host] Create backend/.venv and install frontend deps

test-local: test-backend-local test-frontend-local ## [host] Run all unit tests

test-backend-local: $(VENV_PY) ## [host] Backend tests (pytest)
	cd backend && $(VENV_PY) -m pytest

test-frontend-local: frontend/node_modules ## [host] Frontend tests (vitest)
	cd frontend && npm test

coverage-local: coverage-backend-local coverage-frontend-local ## [host] Coverage for both sides

coverage-backend-local: $(VENV_PY) ## [host] Backend coverage -> backend/coverage/html/index.html
	cd backend && $(VENV_PY) -m pytest --cov=app --cov-report=term-missing --cov-report=html --cov-report=xml --cov-report=json

coverage-frontend-local: frontend/node_modules ## [host] Frontend coverage -> frontend/coverage/index.html
	cd frontend && npm run test:coverage

clean-local: ## [host] Remove backend/.venv, frontend/node_modules and coverage output
	rm -rf $(VENV) frontend/node_modules backend/coverage frontend/coverage

# --- Unit-test agent pipeline (same code as the GitHub workflow) ---------------
#   make pipeline                         base=origin/main, head=HEAD
#   make pipeline BASE=main HEAD=WORKTREE test uncommitted changes, no commit needed
#   make backfill                         whole-repo coverage backfill
# Publishing is a dry-run locally: see .agent-out/pr-comment.md and .agent-out/final.patch
# (apply with: git apply .agent-out/final.patch).
# Model credentials + limits: .env (make env, then fill ANTHROPIC_API_KEY).

# Agent config + credentials: .env in the repo root (gitignored, see .env.example), read by
# pipeline.py itself: the key is passed only to the agent process, never to npm/pip or tests.
# UTA_ENV_FILE=~/.config/cloudfide/agent.env (chmod 600) keeps the key outside the repo.
UTA_ENV_FILE ?= $(CURDIR)/.env

BASE ?= origin/main
HEAD ?= HEAD
PIPELINE := python3 .github/agent-scripts/pipeline.py --base $(BASE) --head $(HEAD)
PIPELINE_ENV := TASKLY_PYTHON=$(VENV_PY) UTA_ENV_FILE=$(UTA_ENV_FILE)

pipeline: install-local ## [agent] Full local pipeline: prepare -> agent -> verify -> report
	$(PIPELINE_ENV) $(PIPELINE) all $(PIPELINE_ARGS)
	@echo ""; echo "  PR comment preview: .agent-out/pr-comment.md"; echo "  Verified patch:     .agent-out/final.patch"

pipeline-prepare: ## [agent] Snapshot base/head, map changes, decide whether to run the agent
	$(PIPELINE_ENV) $(PIPELINE) prepare $(PIPELINE_ARGS)

pipeline-agent: ## [agent] Run the agent in the prepared workspace + security gate
	$(PIPELINE_ENV) $(PIPELINE) agent $(PIPELINE_ARGS)

pipeline-verify: ## [agent] Independently verify the gated patch (no model involved)
	$(PIPELINE_ENV) $(PIPELINE) verify $(PIPELINE_ARGS)

pipeline-report: ## [agent] Render the PR comment preview
	$(PIPELINE_ENV) $(PIPELINE) report $(PIPELINE_ARGS)

backfill: install-local ## [agent] Coverage backfill over the whole repo (mode=backfill)
	$(PIPELINE_ENV) $(PIPELINE) all --mode backfill $(PIPELINE_ARGS)

test-agent-scripts: $(VENV_PY) ## [agent] Unit tests of the pipeline/skill scripts themselves
	$(VENV_PY) -m pytest -c .github/agent-scripts/tests/pytest.ini .github/agent-scripts/tests
