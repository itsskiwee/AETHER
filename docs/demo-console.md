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

## Presentation walkthrough (pinned-data demo, 18 Oct 2026)

The archive is `runs/demo-pinned/` (or the path given to `scripts/demo.sh`): `configs/demo.yaml`, seed 1000. Its sources sit at 20 pinned EMIT V002 Permian plume locations. Known-good record hashes (canonical JSON): `largest_first` `36b064d9…6ad6`, `adaptive_eig` `8516e1d6…2fdc`. Both are byte-identical in a second process, and both exports reload with every input hash re-verified.

1. Point out **SIMULATED MISSION**, **OFFLINE ARTIFACTS** and **REPLAY**. In the run selector, choose `largest_first`, then `adaptive_eig`. These are separate actual simulator records.
2. Open **Sources**. The counts read *historical plume seeded: 20* and *uniform synthetic fill: 0*. Each source row names the plume it was seeded from. The **EMIT plume context** panel comes from the run's own `input_dataset` reference: dataset `emit-l2b-ch4plm-002-permian-v1` and its manifest SHA-256, observed UTC times (2023–2024), provider file hashes, ten rates shown as *Not estimated (CRITERIA_NOT_MET)*, and an uncertainty meaning of *unknown*. Say plainly that these are historical detections used as locations. They say nothing about activity in the simulated October 2026 scenario, and a missing plume row is not a non-detection. Retrieval time is null (`PARTIAL` evidence), not invented.
3. Open **Windows** (`3`) for spacecraft windows and feasible options; toggle rejected windows to show rejection reasons.
4. Open **Planner** (`5`). Each plan has one independent validation and zero violations (`largest_first`: 41 plans, 37 acquisitions; `adaptive_eig`: 47 plans, 51 acquisitions).
5. The scripted hour-20 forecast (90% cloud on source 0 for 12 h) logs a `forecast_revision` plan: revision 12 for `largest_first`, revision 13 for `adaptive_eig`. **Neither changes its selections, and this is why.** Source 0's only feasible window in the affected interval (`vsat_c:13`, 20:45 UTC) was a candidate but was not selected before the event (p_valid 0.57, EIG 0.267 bits). After the event its utility record shows p_valid 0.077 and EIG 0.036 bits. The forecast changed the window's value as modelled; it simply was not in the plan. Do not present this revision as cloud avoidance.
6. Genuine feedback is visible elsewhere. In `adaptive_eig`, 22 replans triggered by informative acquisitions and 10 routine forecast revisions change the future selections; revision 3 drops nine planned options after new evidence. Compare consecutive revisions' option IDs on **Planner**. A changed plan is a recorded decision difference, not proof of a better outcome.
7. Open **Beliefs** (`4`) and pick a source with acquisitions. Detections and valid non-detections update P(active); invalid acquisitions (24 for `adaptive_eig`, mostly cloud) leave it unchanged. A null measured flux stays absent.
8. Open **Comparison** (`6`). It reads the evaluator output in `runs/demo-pinned/benchmark/`: two development seeds on m0, labelled PRELIMINARY and INSUFFICIENT SAMPLES, with no success verdict. Also say that G4.5 failed for this scenario (`docs/validation-report.md`), so the benchmark as configured is not expected to separate the policies.
9. Open **Method** (`7`) for config hashes, the archived input manifest (`lineage_version` 1, 46 input hashes including all 40 pinned raw files), package versions and limitations.

## Limitations

The spacecraft, source behavior, sensor response, and weather are simulated under
explicit assumptions. This prototype does not establish real-world attribution,
real emission reductions, or real mission capability. The demo contains a scripted
forecast event. Development-seed comparisons are preliminary; the protocol remains
unlocked and no holdout result is implied. Solver runtime may be absent from
deterministic run records; “Not recorded” is not a measured zero. A missing artifact
or API error is displayed rather than replaced by a result.

Historical EMIT rows are provider detections from the years in the pinned manifest.
They are location context only: they do not describe the source's activity at the
virtual scenario epoch, set simulated truth, or turn absent plume rows into
non-detections. A numeric uncertainty whose provider meaning is unknown is shown
with that unknown meaning rather than interpreted as an interval or standard
deviation. The comparison screen shows registered family coverage and the separate
measured timing sidecar when those artifacts are present; timing is complete-run
wall time, not solver runtime.

In the pinned demo, the injected hour-20 cloud event lowers the utility of the target source's
only affected window, which neither policy had selected; neither revision changes its
selections (step 5). The demo establishes a logged, forecast-caused planning revision and
evidence-driven selection changes. It does not establish targeted cloud avoidance. G1-F fails
for this scenario: pass `vsat_d:13` can hold at most two acquisitions.

## Rehearsal evidence (pinned demo)

See the end of `docs/lanes/completion-claude-1.md` for the final-revision browser, API and Axe results on `runs/demo-pinned`.

## Historical rehearsal evidence (17 Oct, synthetic-placement demo in `AETHER/runs/demo`)

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
