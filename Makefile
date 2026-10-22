.PHONY: install test lint run-api run-demo run-dashboard run-sap-sandbox

install:
	python -m pip install -e ".[dev]"

test:
	python -m pytest

lint:
	python -m ruff check src tests scripts infra sandbox

run-api:
	python -m uvicorn chainmind.api.main:app --app-dir src --reload

run-demo:
	python scripts/run_demo.py

run-dashboard:
	cd dashboard && npm run dev

run-sap-sandbox:
	python -m uvicorn sap_sandbox.main:app --app-dir sandbox --host 127.0.0.1 --port 8100 --reload
