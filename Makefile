# One-command start for the whole project.
#
#   make up      start everything and print the links
#   make down    stop everything (the database data is kept)
#   make help    all commands
#
# Needs: Docker (running), Python 3.11+, Node.js. Runs on macOS and Linux.

BACKEND_PORT := 8000
MOBILE_PORT  := 8081
# 127.0.0.1 keeps the backend private to this computer. Use `make up HOST=0.0.0.0` for a real phone (Expo Go)
# or for Prometheus on Linux. That also opens /docs and /metrics to your network.
HOST ?= 127.0.0.1

PY  := .venv/bin/python
RUN := .run

.DEFAULT_GOAL := help
.PHONY: help up down restart status logs mobile reset test lint

help: ## Show this list
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/^([a-z]+):.*## /  make \1\t/'

# ---------------------------------------------------------------- setup (runs only when needed)

$(RUN):
	@mkdir -p $(RUN)

.env:
	@cp .env.example .env
	@echo "Created .env from .env.example"

mobile/.env:
	@cp mobile/.env.example mobile/.env

$(RUN)/deps.stamp: requirements.txt | $(RUN)
	@test -d .venv || python3 -m venv .venv
	@echo "Installing Python packages (first run takes a minute)..."
	@.venv/bin/pip install -q -r requirements.txt
	@touch $@

mobile/node_modules: mobile/package.json
	@echo "Installing app packages (first run takes a few minutes)..."
	@cd mobile && npm install --no-audit --no-fund
	@touch $@

# ---------------------------------------------------------------- commands

up: .env mobile/.env $(RUN)/deps.stamp mobile/node_modules ## Start everything and print the links
	@docker info >/dev/null 2>&1 || { echo "Docker is not running. Start Docker Desktop and run make up again."; exit 1; }
	@echo "Starting PostgreSQL, Prometheus and Grafana..."
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
	@# terminal's output open, so `make up | tee log` would never return.
	@{ cd mobile && CI=1 exec npx expo start --web --port $(MOBILE_PORT); } > $(CURDIR)/$(RUN)/mobile.log 2>&1 < /dev/null &
	@for i in $$(seq 1 60); do curl -sf -o /dev/null http://localhost:$(MOBILE_PORT) && break; sleep 0.5; done
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
	@echo "  iOS simulator or a phone: make mobile      Logs: make logs      Stop: make down"
	@grep -Eq '^ANTHROPIC_API_KEY=.+' .env || { echo ""; echo "  WARNING: ANTHROPIC_API_KEY is empty in .env, so the agent cannot answer yet."; echo "  Put your key in .env, then run: make restart"; }

stop-apps:
	@lsof -ti tcp:$(BACKEND_PORT) -sTCP:LISTEN | xargs kill 2>/dev/null || true
	@lsof -ti tcp:$(MOBILE_PORT) -sTCP:LISTEN | xargs kill 2>/dev/null || true

down: stop-apps ## Stop everything (database data is kept)
	@docker compose --profile observability down
	@echo "Stopped."

restart: down up ## Stop and start again (use after changing .env)

status: ## What is running
	@printf "backend    "; curl -sf -o /dev/null http://localhost:$(BACKEND_PORT)/metrics && echo "up   http://localhost:$(BACKEND_PORT)/docs" || echo "down"
	@printf "mobile web "; curl -sf -o /dev/null http://localhost:$(MOBILE_PORT) && echo "up   http://localhost:$(MOBILE_PORT)" || echo "down"
	@docker compose --profile observability ps --format 'table {{.Name}}\t{{.Status}}' 2>/dev/null || echo "docker is not running"

logs: ## Follow the backend log
	@tail -n 40 -f $(RUN)/backend.log

mobile: ## Interactive Expo: press i for the iOS simulator, or scan the QR code with Expo Go
	@lsof -ti tcp:$(MOBILE_PORT) -sTCP:LISTEN | xargs kill 2>/dev/null || true
	@cd mobile && npx expo start

reset: ## Wipe and reload the demo data (database must be running)
	@$(PY) -m seed.seed

test: ## Run the backend tests (start Docker first, or the PostgreSQL tests are skipped)
	@$(PY) -m pytest -q

lint: ## Check the code style
	@.venv/bin/ruff check app tests seed loadtest scripts
