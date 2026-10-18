.PHONY: check lint types layers docs test fmt

DOCS = README.md CHANGELOG.md docs tenants src/fdeops/agent/prompts

check: lint types layers docs test

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

types:
	uv run mypy src

layers:
	uv run lint-imports

# ASD-STE100 Simplified Technical English for all documents
docs:
	uv run fdeops docs check $(DOCS)

test:
	uv run pytest

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests
