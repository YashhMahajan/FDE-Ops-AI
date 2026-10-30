.PHONY: check lint types layers docs test fmt security docs-truth

DOCS = README.md SECURITY.md CONTRIBUTING.md docs tenants src/fdeops/agent/prompts

check: lint types layers docs test

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

types:
	uv run mypy src

layers:
	uv run lint-imports

# Text check for all documents
docs:
	uv run fdeops docs check $(DOCS)

test:
	uv run pytest

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests

# Licenses of the runtime dependencies, and known vulnerabilities (needs the network)
security:
	uv run python scripts/license_check.py
	uv export --locked --all-extras --no-dev --no-hashes --no-emit-project > /tmp/fdeops-req.txt
	uvx pip-audit==2.9.0 --strict -r /tmp/fdeops-req.txt

# Each link, each named command and each runnable command in the documents
docs-truth:
	uv run python scripts/check_docs.py
