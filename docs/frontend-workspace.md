# Connected mission workspace

The frontend now has one application shell and navigation for provider context,
recorded missions, comparison results, configuration and evidence. Its design uses
a dark navigation rail, a light analysis canvas, clear provenance labels and actual
artifact metrics. There are no fabricated live values or simulated run controls.

## Navigation

| View | Connected data and actions |
|---|---|
| Mission overview | Selected RunRecord, source locations, model P(active), recorded outcomes/events, measured timing and connection state. Selecting a location and Inspect source lineage opens its highlighted source row. |
| Satellite context | `/api/live-context`: real Landsat orbital inputs, propagated positions and NASA catalogue metadata, with timestamps, stale/error states and hashes. |
| Sources & observations | Recorded source hypotheses, their coordinates and run-pinned real historical plume records. Missing rates stay null. |
| Observation windows | Selected run's feasible/rejected windows, opportunities and rejection reasons. |
| Mission planner | Actual plan revisions, candidates, utilities, selections and logged replan causes. |
| Belief history | Recorded model inference and simulated outcome markers for the selected source. |
| Policy comparison | Completed evaluator CSV/interval artifacts, two-seed preliminary status, coverage, denominators and timing. No browser-generated scientific replacements. |
| Scenario & instruments | Current project YAML-derived virtual spacecraft, simulated sensor profiles and planner settings. These are distinct from the selected run's immutable identity. |
| Evidence & exports | Run/config identities, full manifest, recorded research gate status, timing JSON and the actual verified ZIP export. |

The run selector is shared across simulation views. Navigation uses query parameters
and supports browser history. `?view=live` remains a direct satellite-context link.
API access is available from the top bar. Refresh connected data reloads the current
run and independent resources; it does not rerun simulations or download from each
provider per visitor. Missing sidecars remain unavailable, never zero or sample values.

## Deployment and evidence

Use the README commands or `scripts/serve_hosted.sh`. Both single-origin deployment
and the older `scripts/serve-demo.sh` path now use the same full API application.
The repository's recorded sample includes accepted exports and completed development
comparison files. To generate a new reproducible sample from accepted artifacts:

```bash
python scripts/prepare_hosted_replay.py --demo runs/demo-pinned \
  --destination data/fixtures/hosted_replay_v2 --include-comparison
```

The producer refuses an existing destination and validates accepted run hashes and
export identity. It only copies known artifact names; caches, unfinished run jobs
and credentials are excluded. Research status is read from recorded gate artifacts,
not inferred from styling or a successful software build.

## Checks and limits

Production TypeScript/Vite build and scoped Python Ruff checks passed. Actual
same-origin requests returned the run index, each run's timing JSON and downloadable
ZIP, live context, preliminary confidence intervals, measured comparison timing,
recorded research status and frontend HTML/assets. Both downloaded ZIPs matched
their selected run IDs. The recorded sample was reproduced with the preparation
command and its file hashes regenerated.

No browser was available in the computer-use environment, so a new visual,
keyboard or Axe rehearsal is not claimed. Existing browser automation expectations
describe the previous shell and need review for this navigation redesign before
being treated as release evidence. Docker image verification remains blocked by
daemon permissions. Scientific acceptance and public hosting remain separate.
