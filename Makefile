.PHONY: install run test lint format pre-commit docker-build docker-run

install:
	uv sync

run:
	uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8001

test:
	uv run pytest

lint:
	uv run ruff check src tests
	uv run mypy src

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

pre-commit:
	uv run pre-commit install

docker-build:
	docker build -t telegram-scraper-service .

docker-run:
	docker run -p 8001:8001 telegram-scraper-service
