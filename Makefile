export PYTHONPATH := src
export MPLBACKEND := Agg

.PHONY: install test lint typecheck check compile ingest api worker worker-once docker-config docker-build docker-up docker-down smoke clean

# Mesmas versões do CI e da imagem Docker (uv.lock).
install:
	uv sync --locked

test:
	uv run pytest -q

lint:
	uv run ruff check .

typecheck:
	uv run mypy

# Os mesmos gates que o CI aplica.
check: lint typecheck test

compile:
	uv run python -m compileall -q src main.py ingest.py worker.py

ingest:
	uv run python ingest.py

api:
	uv run uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload

worker:
	uv run python worker.py

worker-once:
	uv run python worker.py --once

docker-config:
	docker compose config

docker-build:
	docker compose build

docker-up:
	docker compose up --build

docker-down:
	docker compose down --volumes

smoke:
	curl -fsS http://localhost:8000/health

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
