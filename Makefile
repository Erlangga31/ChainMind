.PHONY: install test lint run-api run-demo run-dashboard

install:
	python -m pip install -e ".[dev]"

test:
	python -m pytest

lint:
	python -m ruff check src tests scripts

run-api:
	python -m uvicorn chainmind.api.main:app --app-dir src --reload

run-demo:
	python scripts/run_demo.py

run-dashboard:
	cd dashboard && npm run dev
