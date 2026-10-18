.PHONY: check lint types layers test fmt

check: lint types layers test

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

types:
	uv run mypy src

layers:
	uv run lint-imports

test:
	uv run pytest

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests
