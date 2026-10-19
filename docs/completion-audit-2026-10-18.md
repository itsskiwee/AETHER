# AETHER completion audit — 18 October 2026

## Finding

The lane work has produced substantial implementation and local verification, but the completion batch is not integrated and the registered scientific experiment is unfinished. The original offline demonstration remains the accepted baseline. There is no demonstrated end-to-end pinned-EMIT release, completed calibration acceptance, locked experiment, or all-family holdout result.

This audit inspected completion reports, Git branches/status, source code, configuration and result artifacts across all eight registered worktrees. It did not rerun test suites or change production code, contracts, configurations or Git history. Test counts below are attributed lane evidence, not a newly verified combined release. A separate pytest process was active in the original AETHER checkout during the audit; its outcome was not available here.

## Where the work actually lives

| Worktree | Observed state | Consequence |
|---|---|---|
| `AETHER` | `ee87199`, original offline demo branch | Preserved baseline, not the completed batch |
| `AETHER-wt/claude-1` | `main`, `302d0b0`, clean | Most recent integration branch: dataset wiring, performance/cache, science drivers and timing aggregation |
| `AETHER-c2` | `886336e`, clean | Newer C2-06 synthetic pilot failure/report, not yet on main |
| `AETHER-c2b` | `1c3e89f`, clean | Performance aggregation branch already represented in main |
| `AETHER-codex1` | `15a7f74`, ingestion changes uncommitted | Parser/inventory/loader/preparer not integrated; 3,372 staged bulk raw-file removals retain local originals |
| `AETHER-codex2` | `ee87199`, orbit/capacity changes uncommitted | Candidate windows, capacity utility/report/tests await integration |
| `AETHER-codex3` | `15a7f74`, checker changes uncommitted | Independent hardening/tests/witness utility await integration |
| `AETHER-codex6` | `15a7f74`, UI/API changes uncommitted | Combined UI patch and latest acceptance report await integration |

The current completion prompt assigns two Claude roles and four Codex roles. The original build used six Codex roles. In this batch, `completion-codex-4.md` and `completion-codex-6.md` describe the same UI worktree; the latter is an earlier in-progress handoff. These are not two independent delivered UI implementations. Do not count worktrees or duplicate reports as completed task counts.

The completion reports inside codex1 are older copies of Claude-1 status. The latest Claude-1 report is in its own worktree. Claude-2’s completion report is also stale relative to its committed C2-06 pilot artifact. Its validation report retains an old gate table saying “Not run” alongside the newer pilot-failure discussion; reconcile these by scope and date.

## Completed implementation and bounded evidence

- Ingestion: actual V002 spaced-key parsing, full inventory, deterministic sample selection/preparer and strict pinned loader exist in codex1. Reported inventory: 1,686 metadata/raster pairs, 155 regional records, 73 numeric rates, 82 missing rates and 144 regional clusters. Reported local checks: 305 backend tests, ingestion checks and clean Ruff. This does not certify the merged code.
- Integration: main has `SourcesConfig.plume_dataset`, `InputDatasetRef`, source resolution, explicit synthetic mode for windows/simulate, run performance contracts/artifacts and geometry caching. Base still selects `plume_dataset: null`.
- Science: main has the resumable run matrix, G4.5 driver, calibration analysis and SCI-08 descriptive comparison. Historical flux comparison is not population-prior validation. Provider uncertainty remains UNKNOWN; persistence assumptions remain unverified.
- Orbit: codex2 reports 14 focused tests and pinned offline replay. Synthetic candidate has six feasible passes, 5–10 optimized acquisitions per pass and zero checker violations. Historical-location candidate has seven passes, one supporting only two acquisitions: a recorded G1-F failure. Per-pass independent capacities are not total mission throughput.
- Verification: codex3 adds candidate/time/lookahead/exposure checks and committed-replan geometry regression; reports 500 solver/oracle instances, independent geometry checks and a passing local offline suite. Its completion file’s remaining-capacity note predates the independent historical-candidate confirmation recorded by codex2. Neither closes capacity on the final immutable integrated dataset.
- UI/API: the newer `completion-codex-4.md` reports 24 API tests, a successful production build, 16 browser passes plus one optional skip, separate real API replay of the old demo, and zero serious/critical Axe findings. Actual pinned-EMIT browser replay remains unavailable. Preserve explicit synthetic-only and unavailable states.

## Blocking findings

### 1. DATA-01 cannot currently produce its final deliverable

All inspected `DataSource` contracts still declare `retrieved_at_utc: UtcDatetime`. The proposed interface and preparer require null when retrieval time is unknown. `prepare_pinned.py` explicitly rejects the current contract before writing outputs. The desired nullable-time decision is recorded in codex1’s handoff, but has not been implemented by the contract owner.

`data/manifests/emit_permian.json` and `data/normalized/emit_permian_plumes.json` are absent in every inspected worktree. The 20-record selection exists as code/report, not a usable pinned dataset. Finish the contract adjustment, regenerate the selected sample and normalized input, validate their lineage, and retain the selected permitted metadata/raster pairs in version control. The bulk raw files can remain local/ignored. Bulk historical Git removal is separate optional housekeeping; it is not needed to unblock the sample.

### 2. DATA-02 is implemented only in part

Merge the actual loader/preparer and configure the immutable sample/hash on the integration branch. Reconcile consumers with the final contracts and input reference. Regenerate data-backed windows, demo records, comparison artifacts and exports; demonstrate fair policy-independent source construction and report seeded versus uniform-fill counts.

The current `_dataset_inputs` in main’s `backend/aether/cli.py` returns only the manifest path. Export `input_sha256` therefore does not directly enumerate normalized data and selected raw files as required by the interface. The manifest contains transitive lineage once generated, but the promised export evidence still needs completing and checking. `benchmark` also lacks the explicit `--synthetic-only` CLI switch offered for windows/simulate; implement it or document and review the intended equivalent workflow.

### 3. G1-F has a real failed historical-location candidate

The reported historical-location sample has a pass with two feasible acquisitions against the registered minimum of four. This is a scenario/capacity acceptance problem, not merely a missing report. First establish that its source IDs/coordinates match the final normalized dataset; then rerun on the integrated source construction and independently confirm. If it still fails, prepare a scenario or scope decision with evidence. Do not silently change thresholds or report the passing synthetic candidate as acceptance of the historical dataset. The named `backend/tests/golden/windows_base.json` is also absent on main; candidate review/promotion remains required.

### 4. G4.5 synthetic pilot completed and failed

Authoritative committed artifact: `AETHER-c2/experiments/results/g45-pilot-synthetic-m0/gate.json` (C2-06, `886336e`). It covers m0, 30 development seeds, two references, synthetic placement (`input_datasets: [null]`), and zero reference checker violations.

- Mean random-minus-oracle Brier gap: 0.0047610338.
- Paired SD: 0.0220548674.
- Required 2×SD threshold: 0.0441097347.
- Verdict: false; oracle better on 15/30 seeds.

This is a completed negative pilot, not the final all-six-family pinned-data gate. It must be retained and reported. Merge its result/report, resolve the proposed all-family scope (D9 explicitly requests human sign-off), and evaluate the wired scenario. Scenario/reference/metric changes need the already documented scientific decision process. The proposed h168 diagnostic has no completed gate artifact in the inspected results; do not present its outcome as known.

### 5. Calibration, power and holdout remain outstanding

Calibration analysis exists, but no final multi-seed SCI-10 acceptance artifact was found. Complete the planned m0 calibration with the required reliability/coverage evidence. Derive power from development adaptive-minus-largest paired SD per family, using the approved 0.01 Brier-point minimum effect and 80% power; random-minus-oracle pilot SD is not the substitute.

The protocol is `locked: false`, and no Git tags were listed. No completed registered holdout result was found. Default work sizes, before reuse: 6 families × 30 seeds × 2 reference policies = 360 gate runs; 6 × 30 × 5 competitors = 900 development runs; 6 × N holdout seeds × 5 competitors = 30N holdout runs (3,000 at N=100). Calibration may reuse suitable records. A failed gate can change this execution plan, so do not launch holdout early.

### 6. Freeze enforcement does not yet match the promised identity binding

Main’s `evaluation/protocol.py::verify_git_lock` checks that the protocol is tracked, locally unchanged, and has a containing tag for its last modification. It does not compare current config, dataset, source code, seed files or runtime inputs against a frozen scientific identity. Run-matrix identity hashing helps prevent stale cache reuse, but does not by itself prevent a different scenario/code version from running under an old protocol tag. Add an explicit frozen identity manifest and enforce it at holdout entry, with committed/tagged reviewed inputs and no result-affecting drift.

### 7. Combined acceptance and release evidence remain

After integration, run the required backend, lint, security, production build, browser/accessibility and real API replay checks on one coherent checkout. Existing counts refer to different branch snapshots. Recheck checker/planner handoffs (including the requested explicit `now_utc` call), cache/replay determinism, truth isolation, tamper rejection, dataset hashes, export reloads and performance consumption. Do not mark the full release green from the separate lane suites.

Deliver the P0 requirements-to-evidence matrix, refreshed validation/model cards and walkthrough, all registered family/comparison outputs with CIs and denominators, measured performance and missing-data caveats, final archive/checksums, and required human G5/G6 sign-off. Determine repository private-vulnerability-reporting status separately; this audit did not inspect GitHub settings. Publishing/pushing was not performed.

## Dependency order and effort

1. Consolidate branch/report inventory; integrate reviewed lane changes, nullable retrieval contract and final selected sample.
2. Finish config/export lineage wiring and immutable source construction; produce data-backed pilot, capacity and refreshed demo/API artifacts.
3. Resolve capacity and G4.5 scope/scenario decisions; retain the failed synthetic pilot and independently review the resulting scenario.
4. Complete calibration and development matrix, power/budget decision, and enforce the identity freeze.
5. Commit/tag protocol, then run holdout; report every family and both required comparisons, including negative results.
6. Complete combined acceptance, evidence matrix/archive and human sign-off.

Planning estimate, not a measured schedule: roughly 2–4 engineer-days of integration, verification and reporting if no further scientific/model defects arise, plus experiment compute and scientific decisions. Scenario redesign can add substantial work. Lane reports themselves estimate 1–2 active hours for final independent capacity verification after inputs exist; the earlier UI 1–2-hour patch estimate predates its newer local acceptance and should not be added as unfinished patch work. Do not extrapolate a full benchmark wall time from the old ~450-second geometry pilot: warm caches, policy costs, family costs and worker throughput need a measured integrated pilot.

A single completion percentage would mix implemented code, local tests, failed gates and unrun experiments. The defensible summary is: most core components exist; integration and immutable real-data acceptance are incomplete; the final scientific experiment and release acceptance are still outstanding.
