# Contributing

## Set up

You must have Python 3.11 (or a subsequent version), [uv](https://docs.astral.sh/uv/) and, for the web UI, Node 22 with pnpm 11.

```bash
uv sync
make check
```

`make check` runs the linter, the type checks, the layer contract, the check of the documents and all tests. A change must pass it before you commit it.

You can also use the file `.pre-commit-config.yaml`. It runs the linter and the type check on each commit.

## Rules for a change

1. **Tests.** Each change of behavior has a test. A test must fail when the behavior is wrong. Do not write an assertion that cannot fail.
2. **No secrets.** Do not put keys, tokens or passwords in a file. Put them in environment settings. Refer to `.env.example`.
3. **Layers.** A lower layer must not import a higher layer. The import contract in `pyproject.toml` gives the sequence.
4. **No tenant names in platform code.** Tenant settings go in `tenants/<id>/`. A test makes sure of this.
5. **Database changes.** A change to a table needs a migration. Make it with Alembic, and the migration test examines it.
6. **Dependencies.** Add a dependency only when it is necessary. CI examines its license and its known vulnerabilities.
7. **Documents.** Use the terms in the [glossary](docs/glossary.md). Run `uv run fdeops docs check README.md docs`.
8. **Fictional data only.** Do not add real customer data, real names or real tickets.
9. **Generated documents.** If a change moves a number in `docs/portfolio/generated/`, run `uv run fdeops portfolio` and commit the new documents. A test fails when they show the wrong numbers.
10. **Diagrams.** Change `scripts/make_diagrams.py`, then run `python3 scripts/make_diagrams.py` and `node scripts/render_diagrams.mjs`. Each number in a diagram must come from a record of the repository.
11. **Install test.** A change must not make the base package need a service dependency. CI installs the wheel without extras and runs the commands.

## Database migrations

```bash
uv run fdeops db revision -m "describe the change"
```

The migration test fails if a model changes and no migration changes the schema. Refer to the [runbook](docs/operations/runbook.md) for how to apply migrations in production.

## Commits and pull requests

- One change for each pull request, with its tests and its documents.
- CI must pass: lint, tests on Python 3.11 and 3.12, Postgres, security, the web build and the Docker stack.
- A person reviews each pull request before the merge.
