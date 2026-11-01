# One-command start for the whole project.
#
#   make up      start EVERYTHING in Docker and print the links. Needs only Docker (Python and Node.js are inside the images)
#   make down    stop everything (the database data is kept)
#   make help    all commands
#
# Runs on macOS and Linux. Without `make`, the README has the equivalent `docker compose` command.

BACKEND_PORT := 8000
MOBILE_PORT  := 8081
# Only for `make local`: 127.0.0.1 keeps the backend private to this computer. Use `make local HOST=0.0.0.0` for a
# real phone (Expo Go). That also opens /docs and /metrics to your network.
HOST ?= 127.0.0.1
PYTHON ?= python3

PY  := .venv/bin/python
RUN := .run
# docker-compose.app.yml adds the backend and the app as containers on top of docker-compose.yml
COMPOSE := docker compose -f docker-compose.yml -f docker-compose.app.yml --profile observability
# Stop a process on a port ONLY if it is ours (uvicorn, expo or node). In Docker mode the port is held by Docker's
# own forwarding process, and killing that would take Docker Desktop down.
KILL_OURS = for pid in $$(lsof -ti tcp:$(1) -sTCP:LISTEN 2>/dev/null); do ps -o command= -p $$pid | grep -qE 'uvicorn|expo|node' && kill $$pid 2>/dev/null; done; true
# Is the backend running as a container?
BACKEND_IN_DOCKER = $(COMPOSE) ps --status running --services 2>/dev/null | grep -qx backend

.DEFAULT_GOAL := help
.PHONY: help check-docker up down restart status logs test reset mobile local check lint stop-apps

help: ## Show this list
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z-]+):.*## /  make \1\t/'

.env:
	@cp .env.example .env
	@echo "Created .env from .env.example"

check-docker:
	@command -v docker >/dev/null || { echo "Docker is not installed. Install Docker Desktop: https://www.docker.com/products/docker-desktop/"; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Docker is not running. Start Docker Desktop and run the command again."; exit 1; }

# ---------------------------------------------------------------- everything in Docker

up: check-docker .env ## Start EVERYTHING in Docker (needs only Docker) and print the links
	@$(MAKE) --no-print-directory stop-apps
	@echo "Building and starting everything in Docker (the first build takes a few minutes)..."
	@$(COMPOSE) up -d --build --wait
	@echo ""
	@echo "Everything is running."
	@echo ""
	@echo "  Backend API docs   http://localhost:$(BACKEND_PORT)/docs"
	@echo "  Mobile app (web)   http://localhost:$(MOBILE_PORT)"
	@echo "  Prometheus         http://localhost:9090"
	@echo "  Grafana            http://localhost:3000   (Dashboards > Luwo list agent, no login)"
	@echo ""
	@echo "  Demo logins        aigul@luwo.test (teacher), admin1@luwo.test (school admin), root@luwo.test (superadmin)"
	@echo "  Password           demo1234 (or tap a demo button on the login screen)"
	@echo ""
	@echo "  Logs: make logs     Tests: make test     iOS simulator or a phone: make mobile (needs Node.js)     Stop: make down"
	@grep -Eq '^ANTHROPIC_API_KEY=.+' .env || { echo ""; echo "  WARNING: ANTHROPIC_API_KEY is empty in .env, so the agent cannot answer yet."; echo "  Put your key in .env, then run: make up"; }

stop-apps:
	@$(call KILL_OURS,$(BACKEND_PORT))
	@$(call KILL_OURS,$(MOBILE_PORT))

down: stop-apps ## Stop everything, in either mode (database data is kept)
	@$(COMPOSE) down --remove-orphans
	@echo "Stopped."

restart: down up ## Stop and start again (use after changing .env)

status: ## What is running
	@printf "backend    "; curl -sf -o /dev/null http://localhost:$(BACKEND_PORT)/docs && echo "up   http://localhost:$(BACKEND_PORT)/docs" || echo "down"
	@printf "mobile web "; curl -sf -o /dev/null http://localhost:$(MOBILE_PORT) && echo "up   http://localhost:$(MOBILE_PORT)" || echo "down"
	@$(COMPOSE) ps --format 'table {{.Name}}\t{{.Status}}' 2>/dev/null || echo "docker is not running"

logs: ## Follow the backend log
	@if $(BACKEND_IN_DOCKER); then $(COMPOSE) logs -f --tail 40 backend; else tail -n 40 -f $(RUN)/backend.log; fi

test: check-docker ## Run the backend tests inside Docker (needs only Docker)
	@$(COMPOSE) up -d --wait db
	@$(COMPOSE) run --rm --no-deps -T --entrypoint python \
		-v $(CURDIR)/tests:/srv/tests -v $(CURDIR)/pytest.ini:/srv/pytest.ini \
		-e TEST_DATABASE_URL=postgresql+asyncpg://luwo:luwo@db:5432/luwo_test \
		backend -m pytest -q

reset: ## Wipe and reload the demo data (the database must be running)
	@if $(BACKEND_IN_DOCKER); then $(COMPOSE) exec -T backend python -m seed.seed; else $(PY) -m seed.seed; fi

mobile: ## Interactive Expo: press i for the iOS simulator, or scan the QR code with Expo Go (needs Node.js)
	@command -v node >/dev/null && command -v npm >/dev/null || { echo "Node.js is needed for this (https://nodejs.org). The browser version works without it: make up."; exit 1; }
	@test -d mobile/node_modules || { echo "Installing app packages (first run takes a few minutes)..."; cd mobile && npm install --no-audit --no-fund; }
	@test -f mobile/.env || cp mobile/.env.example mobile/.env
	@$(COMPOSE) rm -sf mobile >/dev/null 2>&1 || true
	@$(call KILL_OURS,$(MOBILE_PORT))
	@cd mobile && npx expo start

# ---------------------------------------------------------------- the alternative: backend and app on YOUR machine

check: ## (for make local) Check that Docker, Python 3.11+ and Node.js are installed
	@command -v docker >/dev/null || { echo "Docker is not installed. Install Docker Desktop: https://www.docker.com/products/docker-desktop/"; exit 1; }
	@command -v node >/dev/null && command -v npm >/dev/null || { echo "Node.js is not installed (the mobile app needs it). Install the LTS version: https://nodejs.org"; exit 1; }
	@test -d .venv || $(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null || { echo "Python 3.11 or newer is needed (found: $$($(PYTHON) --version 2>&1)). Install it from https://www.python.org/downloads/ , then run: make local PYTHON=python3.12"; exit 1; }
	@echo "Docker, Python and Node.js are installed."

$(RUN):
	@mkdir -p $(RUN)

mobile/.env:
	@cp mobile/.env.example mobile/.env

$(RUN)/deps.stamp: requirements.txt | $(RUN)
	@test -d .venv || $(PYTHON) -m venv .venv
	@echo "Installing Python packages (first run takes a minute)..."
	@.venv/bin/pip install -q -r requirements.txt
	@touch $@

mobile/node_modules: mobile/package.json
	@echo "Installing app packages (first run takes a few minutes)..."
	@cd mobile && npm install --no-audit --no-fund
	@touch $@

local: check .env mobile/.env $(RUN)/deps.stamp mobile/node_modules ## Backend and app on YOUR machine instead of Docker (needs Python 3.11+ and Node.js)
	@echo "Starting PostgreSQL, Prometheus and Grafana..."
	@$(COMPOSE) rm -sf backend mobile >/dev/null 2>&1 || true
	@docker compose --profile observability up -d --wait
	@echo "Preparing the database..."
	@.venv/bin/alembic upgrade head > $(RUN)/alembic.log 2>&1 || { cat $(RUN)/alembic.log; exit 1; }
	@# Seed only an empty database: the seed script wipes the demo data (make reset does that on purpose)
	@if [ "$$(docker compose exec -T db psql -U luwo -d luwo -tAc 'select count(*) from users' | tr -d '[:space:]')" = "0" ]; then \
		echo "Loading demo data..."; $(PY) -m seed.seed; \
	fi
	@$(MAKE) --no-print-directory stop-apps
	@echo "Starting the backend..."
	@nohup .venv/bin/uvicorn app.main:app --host $(HOST) --port $(BACKEND_PORT) > $(RUN)/backend.log 2>&1 < /dev/null &
	@for i in $$(seq 1 40); do curl -sf -o /dev/null http://localhost:$(BACKEND_PORT)/metrics && break; sleep 0.5; done
	@curl -sf -o /dev/null http://localhost:$(BACKEND_PORT)/metrics || { echo "The backend did not start. See: make logs"; exit 1; }
	@echo "Starting the mobile app (web version)..."
	@# The braces and the redirect are on purpose: `cd x && cmd &` would background the whole group and keep this
	@# terminal's output open, so `make local | tee log` would never return.
	@{ cd mobile && CI=1 exec npx expo start --web --port $(MOBILE_PORT); } > $(CURDIR)/$(RUN)/mobile.log 2>&1 < /dev/null &
	@for i in $$(seq 1 60); do curl -sf -o /dev/null http://localhost:$(MOBILE_PORT) && break; sleep 0.5; done
	@echo ""
	@echo "Everything is running (backend and app on your machine, the rest in Docker)."
	@echo ""
	@echo "  Backend API docs   http://localhost:$(BACKEND_PORT)/docs"
	@echo "  Mobile app (web)   http://localhost:$(MOBILE_PORT)"
	@echo "  Prometheus         http://localhost:9090"
	@echo "  Grafana            http://localhost:3000   (Dashboards > Luwo list agent, no login)"
	@echo ""
	@echo "  Logs: make logs     iOS simulator or a phone: make mobile     Stop: make down"
	@grep -Eq '^ANTHROPIC_API_KEY=.+' .env || { echo ""; echo "  WARNING: ANTHROPIC_API_KEY is empty in .env, so the agent cannot answer yet."; echo "  Put your key in .env, then run: make local"; }

lint: ## Check the code style (needs make local once, for the Python environment)
	@.venv/bin/ruff check app tests seed loadtest scripts
