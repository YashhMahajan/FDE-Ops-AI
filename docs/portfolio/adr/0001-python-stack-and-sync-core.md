# 0001: Python, Pydantic and a Synchronous Core

*Status: accepted.*

## Context

The platform evaluates agents, calculates statistics and serves an API. Most AI tools and libraries use Python. The author must explain each part in an interview. The evaluation runs many episodes at the same time, but each episode is a sequence of steps.

## Decision

- Python 3.11 or a subsequent version, with `uv` for packages and a lock file.
- Pydantic models with `extra="forbid"` for each configuration and each record. Thus, a wrong key in a YAML file stops the load.
- A synchronous core. The runner uses a thread pool for parallel episodes. Only the API layer uses FastAPI.
- An import contract (import-linter) with layers. A lower layer cannot import a higher layer.

## Alternatives

- **Async code from the core to the API.** Async code makes each function more complex. The model calls are the slow part, and a thread pool is sufficient for them.
- **Dataclasses without validation.** A configuration error then occurs late, in a run, not at load time.

## Results

- The core is easy to test without an event loop.
- A change that breaks the layers fails in CI.
- A very large evaluation needs more workers, not async code. The job queue gives this.
