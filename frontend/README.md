# AETHER research console

The frontend is a read only viewer for validated `RunRecord` JSON artifacts. It does not simulate
acquisitions, recalculate beliefs, or schedule spacecraft in the browser.

## Run locally

For the complete offline demonstration, follow [the console walkthrough](../docs/demo-console.md).
From the repository root, generate actual artifacts and launch the production console:

```bash
PATH="$PWD/backend/.venv/bin:$PATH" bash scripts/demo.sh
bash scripts/serve-demo.sh
```

For frontend development, install dependencies once, then run the API and Vite in separate terminals:

```bash
cd backend && pip install -e '.[api]' && AETHER_RUNS_DIR=../runs uvicorn aether.api:app --reload
cd frontend && npm run dev
```

The Vite development server proxies `/api` to `http://127.0.0.1:8000`. It loads archived
`runs/<run_id>/run.json` records and falls back to `docs/examples/run.json` when the archive is
empty. The API validates run records with the canonical Pydantic contract. Set
`AETHER_RUNS_DIR` to point to a different run archive.

Benchmark output is read from `AETHER_BENCHMARK_DIR`, defaulting to the `benchmark/` directory
inside the configured run archive. Screen F reads `benchmark-confidence-intervals.json` and the registered
`experiments/protocol.yaml` as well, so it can show paired intervals and protocol decisions without
recomputing them. Without artifacts, each screen displays an explicit empty state. The interface
uses local assets and system font fallbacks, so it can be served without external network access.

With the launcher running against actual demo and evaluator output, run the opt-in browser check:

```bash
AETHER_LIVE_SMOKE=1 CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e -- live-artifacts
```

This check uses the actual API and archive without mocked responses. Ordinary `npm run test:e2e`
uses explicitly identified test fixtures for comparison, accessibility, keyboard, and wording checks.
