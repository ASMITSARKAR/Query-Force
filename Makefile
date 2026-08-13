.PHONY: setup seed-db ingest-rag run verify docker-up

# Cross-platform venv path detection
ifeq ($(OS),Windows_NT)
    VENV_BIN = .venv/Scripts
else
    VENV_BIN = .venv/bin
endif

setup:
	python -m venv .venv
	$(VENV_BIN)/pip install -r requirements.txt

seed-db:
	$(VENV_BIN)/python scripts/seed_data.py

ingest-rag:
	$(VENV_BIN)/python scripts/ingest_schema.py

run:
	$(VENV_BIN)/uvicorn src.api.server:app --reload

verify:
	$(VENV_BIN)/python scripts/verify.py

docker-up:
	docker compose up --build
