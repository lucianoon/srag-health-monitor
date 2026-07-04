PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

export PYTHONPATH := src
export MPLBACKEND := Agg

.PHONY: venv install test compile ingest api worker worker-once docker-config docker-build docker-up docker-down smoke clean

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

test:
	PYTHONPYCACHEPREFIX=/private/tmp/srag_pycache MPLCONFIGDIR=/private/tmp/srag_mplconfig $(VENV_PYTHON) -m unittest discover -s tests -p "test*.py"

compile:
	PYTHONPYCACHEPREFIX=/private/tmp/srag_pycache MPLCONFIGDIR=/private/tmp/srag_mplconfig $(VENV_PYTHON) -m compileall -q src main.py worker.py ingest.py tests

ingest:
	$(VENV_PYTHON) ingest.py

api:
	$(VENV)/bin/uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload

worker:
	$(VENV_PYTHON) worker.py

worker-once:
	$(VENV_PYTHON) worker.py --once

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
