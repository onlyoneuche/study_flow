.PHONY: setup dev dev-backend dev-frontend test test-backend test-frontend test-browser build docker-up docker-down

export UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
export npm_config_cache ?= $(CURDIR)/.cache/npm
export NEXT_TELEMETRY_DISABLED = 1

setup:
	uv sync --directory backend --frozen
	backend/.venv/bin/python scripts/init_env.py
	npm --prefix frontend ci

dev:
	backend/.venv/bin/python scripts/dev.py

dev-backend:
	uv run --directory backend uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000

dev-frontend:
	npm --prefix frontend run dev

test: test-backend test-frontend

test-backend:
	uv run --directory backend ruff check .
	uv run --directory backend ruff format --check .
	uv run --directory backend pytest

test-frontend:
	npm --prefix frontend test

build:
	npm --prefix frontend run build

test-browser: build
	npm --prefix frontend run test:browser

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down
