.PHONY: setup dev test lint db-up db-migrate seed-fixtures

PYTHON ?= python3
VENV ?= .venv
PY := $(VENV)/bin/python

setup:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"

dev:
	$(PY) -m uvicorn app.main:app --host 127.0.0.1 --port 8000

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check .
	$(PY) -m mypy app

db-up:
	@echo "Milestone 1 uses local SQLite; no Docker service is required."

db-migrate:
	@echo "Milestone 1 creates SQLite tables on app startup; Alembic comes later."

seed-fixtures:
	@echo "Milestone 1 has no crawler fixtures to seed yet."
