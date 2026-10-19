# Codex-4 console/API completion status — 18 October 2026

Assignment: Codex-4 in `Implementation/Six_Model_Completion_Prompt.md` (console,
artifact display, API, UI/API tests, walkthrough and comparison docs). Worktree:
`/home/itsskiweee/Projects/AETHER-codex6`, branch `lane/UI-08-completion`.

## Implemented in this lane

- Added read-only APIs for project and run-pinned historical context, run input
  manifests, measured development timing, and protocol family/policy rosters.
  Historical inputs are hash checked and validated before display. Old runs do
  not inherit a dataset from the current project configuration.
- Added an EMIT context view with provenance, dates, location, provider source
  hashes, nullable rate and reason, uncertainty kind, citation and retrieval
  evidence. The parser fixture remains visibly synthetic and separate.
- Added plume-seeded versus uniform-fill markers/counts, simulated acquisition
  labels, artifact family/policy coverage, confidence intervals and sample
  counts, preliminary/locked status, and complete-run timing with an explicit
  unavailable state.
- Updated `docs/demo-console.md`, `docs/demo-comparison.md`, and the frontend
  README with the data semantics and walkthrough.

## Verification

- `backend/.venv/bin/python -m pytest tests/unit/test_api.py -q`: 24 passed
  after the final explicit-null regression case was added.
- `backend/.venv/bin/ruff check aether/api/__init__.py tests/unit/test_api.py`:
  passed.
- `npm run build`: passed (`tsc -b && vite build`).
- Focused Playwright run for comparison, historical context, project EMIT
  context, and manifest/error states: 4 passed.
- Full offline backend suite: passed (exit 0); the final explicit-null regression
  was added afterward and passed in the focused API run above.
- Full Ruff check and format check: passed (68 files already formatted).
- Full Playwright suite: 16 passed, 1 skipped. Both run and project Axe audits
  reported zero serious or critical violations across all seven screens. The
  skipped case is the opt-in live replay.
- Opt-in live replay against the preserved `/home/itsskiweee/Projects/AETHER/runs/demo`
  archive: 1 passed with no route mocks. The API reloaded two actual simulated run
  records, run manifests, and evaluator outputs; the browser opened the archived
  input hashes/package versions on Method. Both historical-context requests
  correctly returned unavailable because those old runs have no pinned dataset
  reference.

## Integration evidence and limits

For plume observations, this worktree contains only
`data/manifests/synthetic_ingestion_examples.json`; the project configuration
does not yet select `sources.plume_dataset`, and the current run contract has no
`input_dataset` field. Therefore the real EMIT
manifest cannot yet be replayed in the console, and older runs explicitly show
that their historical dataset reference is unavailable. The API and display
path are ready for Codex-1's pinned manifest and Claude-1's run/config wiring.
No real plume records, scientific acceptance, protocol lock, or holdout result
are claimed here. The current protocol has six registered families and remains
preliminary/unlocked.
