# Offline demonstration console

This is a **SIMULATED MISSION**. The read-only console replays actual `RunRecord`
artifacts produced by the simulator. It does not task real spacecraft. It needs
no credentials or network access after dependencies and pinned ephemeris data
are installed.

## Setup

From the repository root, use Python 3.12 or newer and Node.js 18 or newer:

```bash
python -m venv backend/.venv
backend/.venv/bin/pip install -e './backend[dev,geo,api]'
npm --prefix frontend ci
```

The repository's pinned `data/ephemeris/de421.bsp` must be present. Installation
requires access to package registries; demonstration generation and replay run offline.

The exact backend installation above was rehearsed in a fresh temporary environment
on 17 October 2026 with Python 3.14.7. All 14 API tests passed with FastAPI 0.143.3,
Starlette 1.8.0, httpx 0.28.1, Pydantic 2.14.1, and uvicorn 0.54.0. Starlette emits
a nonblocking httpx deprecation warning; no API test hung.

## Generate and serve

```bash
bash scripts/demo.sh
```

This runs `configs/demo.yaml`, seed `1000`, for `largest_first` and `adaptive_eig`.
The script checks every plan's independent validation, reconstructs inference from the
acquisition records, repeats both runs in a separate process for byte-identical replay,
and verifies exported ZIP records and checksums. It then runs the base-config comparison
for largest-first, adaptive EIG, and greedy EIG on development seeds 1000 and 1001.
The measured one-seed comparison pilot took about 6.6 minutes; allow time for the
demo runs, replay, and two-seed comparison when regenerating.
Keep the generated `runs/demo/` archive and ZIP exports outside Git.

```bash
bash scripts/serve-demo.sh
```

Open <http://127.0.0.1:4173>. This builds the production console and starts the
read-only API on port 8000 and console on port 4173, bound to localhost. Ctrl-C
stops both. Both ports must be free. To replay a separately packaged artifact
directory, pass its path as the launcher's first argument. `AETHER_PYTHON` may
specify another Python executable with the backend installed.
If either port is occupied, set `AETHER_API_PORT` and `AETHER_CONSOLE_PORT`, for
example `AETHER_API_PORT=8001 bash scripts/serve-demo.sh`.

The comparison reads evaluator files from `runs/demo/benchmark/`, or the absolute
directory in `AETHER_BENCHMARK_DIR`. Comparison generation uses `configs/base.yaml`;
the scripted demo weather event is excluded from benchmark data. Missing evaluator
output remains explicitly unavailable in the console.

## Presentation walkthrough

1. Point out **SIMULATED MISSION**, **OFFLINE ARTIFACTS**, and **REPLAY**. In the
   run selector, choose `largest_first`, then `adaptive_eig`; these are separate
   actual simulator records, each with seed 1000.
2. Open **Windows** (or press `3`) to inspect spacecraft windows and the table
   of feasible options. Toggle rejected windows to inspect rejection reasons.
3. Open **Planner** (`5`). Select a plan revision and inspect its actual option
   IDs, candidate utility records, independent-checker version, and violation
   count. A successful archive has one independent validation per plan and zero
   violations.
4. Select a revision whose cause is `forecast_revision`. Expand **Recorded
   forecast events** to see the event time and payload. Inspect the previous
   revision's added/removed option IDs. Describe the recorded difference; a
   replan can retain the same choices, and does not guarantee an improvement.
   The injected event is at simulation hour 20. In the known-good `largest_first`
   run it causes revision 10, whose selections remain unchanged. The event targets
   `source-001`, which has no feasible observation window during the affected
   interval, hours 20–32. For largest-first, this records a forecast-triggered planning revision with
   no selection change. The scenario was
   retained without tuning it to manufacture a difference.
   In `adaptive_eig`, the same event causes revision 11 and selections do change.
   Its candidate set remains the same 16 windows; 11 option IDs are removed and
   9 are added. Forecast issuance advances from hour 18 to hour 20 and refreshes
   weather estimates for other sources. Because `source-001` has no feasible
   window in the affected interval, this is a forecast-refresh-triggered selection
   difference, not evidence of avoiding that source's scripted cloud event.
5. Open **Beliefs** (`4`) and select a source with acquisitions. Inspect
   P(active), the values table, and the evidence ledger. Detection and valid
   non-detection are emission evidence; invalid and unobserved outcomes are
   distinct. Null measured flux remains absent.
6. Open **Comparison** (`6`). This reads evaluator output rather than deriving
   claims from the selected demo run. Show sample counts, paired differences,
   intervals when defined, and the preliminary/insufficient-samples label for
   fewer than 10 seeds. A single-seed pilot establishes execution, not superiority.
7. Open **Method** (`7`) for configuration hashes, code identity, provenance,
   and limitations.

## Limitations

The spacecraft, source behavior, sensor response, and weather are simulated under
explicit assumptions. This prototype does not establish real-world attribution,
real emission reductions, or real mission capability. The demo contains a scripted
forecast event. Development-seed comparisons are preliminary; the protocol remains
unlocked and no holdout result is implied. Solver runtime may be absent from
deterministic run records; “Not recorded” is not a measured zero. A missing artifact
or API error is displayed rather than replaced by a result.

The injected hour-20 cloud event affects a source with no feasible window in its
hours-20–32 interval. The demonstrated `largest_first` revision retains its
selections; `adaptive_eig` revision 11 changes selections with the same 16 candidate
windows and globally refreshed forecast estimates. This does not establish
targeted cloud avoidance. Both runs establish a logged
planning revision caused by forecast issuance.

## Rehearsal evidence

The production launcher was rehearsed against `runs/demo/` using the fresh Python
environment described above, API port 8001, and console port 4173. The actual
`largest_first` seed-1000 archive loaded through the API and browser with 40 plans,
40 independent validation records, zero violations, and 35 acquisitions. Windows,
source-selected belief history, injected-event revision 10, comparison missing-data
state, and method screens rendered with no browser page errors. Screenshots are
stored outside Git in `runs/demo/rehearsal/largest-*.png`. This is execution evidence;
it is not a comparative performance claim.

The same browser walkthrough also passed for the actual `adaptive_eig` seed-1000
archive: 52 plans, 52 independent validations, zero violations, and 47 acquisitions.
Injected-event revision 11 shows the recorded option changes and event payload.
Screenshots are in `runs/demo/rehearsal/adaptive-*.png`; no browser page errors occurred.

An opt-in Playwright smoke using the actual one-seed pilot comparison passed against both actual archives and the actual
evaluator comparison through the production proxy (1 test, 2.6 seconds). It verified
the injected event's exact revision time, independent validation counts, visible
acquisition outcomes, and comparison policy pairs/sample counts. The comparison is
explicitly preliminary with insufficient samples; see
`runs/demo/rehearsal/comparison-actual.png`. No API responses were mocked in this test.

## Known-good artifact set and packaging

The delivery artifact root is `runs/demo/`. Its `acceptance.json` labels the demo
configuration and seed and records byte-identical replay, exported-record reload,
outcome counts, and forecast revision differences. The two policy subdirectories
contain `run.json` and input/package manifests; their ZIP exports are beside them.
`benchmark/` contains actual base-config evaluator output for development seeds
1000 and 1001, all three policies, paired bootstrap intervals, counts, and the
separate measured wall-time sidecar. `replay/` retains the second independent
process's records. `rehearsal/` contains browser screenshots.

Keep this generated output outside Git. To package it separately after the demo
command finishes:

```bash
mkdir -p artifacts
cp docs/demo-console.md runs/demo/WALKTHROUGH.md
tar -czf artifacts/aether-offline-demo-seed1000.tar.gz -C runs demo
sha256sum artifacts/aether-offline-demo-seed1000.tar.gz > artifacts/aether-offline-demo-seed1000.tar.gz.sha256
```

For replay on another installation of this repository, extract the archive into
`runs/`, then run `bash scripts/serve-demo.sh`. Neither simulation regeneration nor
benchmark completion is required to replay the packaged records. Dependencies
must already be installed. To check an existing demo without rerunning simulation:

```bash
backend/.venv/bin/python scripts/verify_demo.py runs/demo
```


Final delivery verification: `bash scripts/demo.sh` exited successfully. Both repeated
demo RunRecords match byte-for-byte; all exported records reload and match their
checksums. The final base-config comparison contains six actual runs (three policies,
two development seeds) and took 631.763 seconds of measured complete-comparison wall
time. Every final run has zero violations and no rejected proposals. The complete
browser suite then passed **13 tests**, including the unmocked two-policy/two-seed
comparison smoke, exact displayed interval values, irregular UTC chart spacing,
keyboard navigation, and zero serious/critical axe findings across all screens.
The offline backend suite passed **294 tests**. Full backend Ruff lint and formatting
of delivery files pass; six earlier formatting-only issues elsewhere are recorded in
the validation report. The production build and launcher clean restart also pass.
