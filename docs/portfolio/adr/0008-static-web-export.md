# 0008: A Static Web UI from an Export

*Language: ASD-STE100. Status: accepted.*

## Context

The web UI must show the release log, gates, the monitor, comparisons, traces, the diagnosis, the roadmap and the business value. The author does not run services on a laptop. A public demo must cost nothing.

## Decision

- `fdeops demo --export` writes JSON files. The Next.js UI is a static export that reads them. It needs no backend and no model.
- The FastAPI service has the same data for a real deployment.
- CI builds the site, serves it, and makes screenshots of each page on desktop, on a phone and in dark mode.

## Alternatives

- **A UI that calls the API.** A demo then needs a server and a database that operate at all times.
- **A notebook.** It does not show the workflow of a release owner.

## Results

- A static host can serve the demo at no cost. A person must approve it before it is public.
- The UI does not show live data. The API does.
