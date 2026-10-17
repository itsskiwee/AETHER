# AETHER research console

The frontend is a read only viewer for validated `RunRecord` JSON artifacts. It does not simulate
acquisitions, recalculate beliefs, or schedule spacecraft in the browser.

## Run locally

Install the frontend dependencies once, then run the API and Vite in separate terminals:

```bash
cd backend && pip install -e '.[api]' && AETHER_RUNS_DIR=../runs uvicorn aether.api:app --reload
cd frontend && npm run dev
```

The Vite development server proxies `/api` to `http://127.0.0.1:8000`. It loads archived
`runs/<run_id>/run.json` records and falls back to `docs/examples/run.json` when the archive is
empty. The API validates run records with the canonical Pydantic contract. Set
`AETHER_RUNS_DIR` to point to a different run archive.

Benchmark output is read from `benchmark-results.csv` beside the configured run directory's
parent. Without artifacts, each screen displays an explicit empty state. The interface uses only
local assets and system font fallbacks, so it can be served without external network access.
