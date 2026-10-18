# P0 requirements-to-evidence matrix (REL-01)

Integrated branch `lane/INT-09-completion-integration` (see the final revision in §Checks). Built on 18 Oct 2026 for the six-hour submission. Status values:

- **PASSED**: verified on this revision, with the evidence named.
- **FAILED**: measured, and below its registered threshold.
- **PENDING**: not run, or waiting on a human decision.
- **OUT OF SCOPE**: excluded by a reviewed scope decision.

Implementation completion is not scientific acceptance. The two are reported separately here.

## A. Stage gates (PRD §3.4 and registered gates)

| Gate | Criterion | Status | Evidence |
|---|---|---|---|
| G0 Data | Provenance-rich real plume records; product fields validated; missing rates safe | **PASSED** | `data/manifests/emit_permian.json` (20 EMIT V002 records, 10 null rates with `CRITERIA_NOT_MET`), `tests/unit/test_pinned_emit_sample.py` (re-derived from the raw JSON without the parser; tamper, missing and edit cases), `tests/unit/test_ingestion.py` |
| G1 Orbit | Geometry, UTC, constraints, frames tested | **PASSED** | `tests/unit/test_orbit_engine.py`, `test_geometry_cross_validation.py` (independent SGP4 + Astropy), pinned DE421/EOP replay test |
| G1-F Capacity | ≥ 5 regional passes / 72 h **and** ≥ 4 acquisitions / pass on the integrated scenario | **FAILED** | 7 passes; per-pass optimum 9, 10, 9, 6, 10, 8, **2** (`experiments/results/g1f-pinned-base/`). The registered contingency (demo → `h168_long_horizon`) awaits a human decision |
| G2 Planner | Independent checker accepts every selected window | **PASSED** | Every demo and gate run has 0 checker violations (`runs/demo-pinned`, gate `reference_checker_violations`); 500-instance CP-SAT/oracle test in `test_checker.py` |
| G3 Inference | Detection / non-detection / no-data cases; probability conservation | **PASSED** (unit) / calibration see SCI-10 | `tests/unit/test_belief.py`, `test_eig.py`; `scripts/verify_demo.py` replays every demo belief update from contracts |
| G4 Feedback | Controlled change alters the posterior and the plan; no hard-coded ordering | **PASSED** | Pinned demo: the injected hour-20 forecast logs a `forecast_revision` (rev 12 / 13) and cuts the target window's p_valid from 0.57 to 0.077. It changes no selection because that window was not selected, as explained in `docs/demo-console.md` step 5. In `adaptive_eig`, 22 evidence-triggered replans change future selections. `scripts/verify_demo.py` replays every belief update |
| G4.5 Discriminability | mean(random − oracle Brier) > 2 SD on 30 tuning seeds, all six families (D9) | **FAILED** (synthetic m0 pilot); pinned all-family: see `docs/validation-report.md` §3.2 | `experiments/results/g45-pilot-synthetic-m0/gate.json`; `experiments/results/g45-pinned-dev/gate.json` |
| SCI-10 Calibration | m0, multi-seed: 90% flux coverage in [0.85, 0.95]; reliability within sampling error (seed-cluster bootstrap) | see `docs/validation-report.md` §3.3 | `experiments/results/sci10-pinned-m0/calibration-m0.json` |
| Power / seed count | Holdout N from adaptive − largest paired SD per family, 0.01 Brier, 80% power | **PENDING** | Needs the 900-run development matrix. It is blocked by the G4.5 scenario decision and would take about 4 h of wall time on 9 workers (measured cost per run, §C) |
| Protocol lock + freeze | `locked: true`, tag, committed scientific identity matched at holdout entry | **PENDING** (mechanism PASSED) | `backend/aether/evaluation/freeze.py`, `tests/unit/test_evaluation_protocol.py` (config, family, data, seed and code drift; dirty tree; late freeze). Nothing is locked or tagged; that waits on the decisions above |
| G5 Science | Held-out seeds, all families, CIs, failure rates | **PENDING** | No holdout has run. A holdout run would be refused by the lock guard |
| G6 Demonstration | Accessible walkthrough; labels evident; offline replay | **PASSED** for the demo scope (human sign-off pending) | `runs/demo-pinned/` (actual pinned-data runs, byte-identical replay, verified exports), browser + Axe in §Checks, `docs/demo-console.md` |

## B. PRD §3.1 P0 mandatory and §21.1 definition of done

| Requirement | Status | Evidence |
|---|---|---|
| Real plume ingestion: timestamp, geometry, provider/product identity, rate if available, uncertainty if available, quality/absence | **PASSED** | Normalized `PlumeObservation`s keep all native properties; `NA` → null + reason; `uncertainty_kind = UNKNOWN` (provider meaning undefined, SCI-08) |
| FR-DATA-003 content hash, retrieved time, citation, adapter and transformation version | **PASSED** (time honestly unknown) | Every record has `source.sha256` = its metadata file and `retrieved_at_utc: null`; the manifest has `retrieval.status: PARTIAL`, adapter and transformation versions |
| FR-DATA-008 demo usable from checked-in permitted sample | **PASSED** | 40 raw files + normalized + manifest tracked; bulk download ignored. Fresh-clone check in §Checks |
| Virtual orbit windows, reproducible trajectory/frames/sensor | **PASSED** | Integrated windows byte-identical to Codex-2's independent candidate (1,494 windows) |
| Feasibility rejection reasons and resource accounting; invalid acquisitions disallowed | **PASSED** | `ObservationWindow.rejection_reasons`; checker rules (overlap, slew, storage, energy, per-orbit, source cap, candidate, lookahead, duration, blackout) |
| Numerical belief update; POD; valid non-detection vs no-data | **PASSED** | Hard rule 3 tests; `verify_demo.py` checks that missing outcomes leave the tensor bit-identical |
| OR-Tools selection; logged status/objective; re-solve on updates | **PASSED** | Plans record `solver_status`, objective and bound; the forecast revision re-solves |
| Deterministic simulation, hidden truth, fixed seed, fair baseline replay | **PASSED** | Byte-identical replay (`runs/demo-pinned/replay`), `test_closed_loop.py`, truth-isolation guard; identical sources/windows across policies |
| Identical candidates/budget/truth for baseline and adaptive | **PASSED** | `test_policies_share_sources_and_windows`; source construction is policy-independent (`resolve_sources`) |
| Objective metric comparison without untested wins | **PASSED** (preliminary only) | Development comparison is labelled PRELIMINARY / insufficient samples; no success verdict |
| Labels distinguish measured, inferred, predicted, simulated | **PASSED** | Provenance classes in contracts and UI; live browser check of pinned context |
| Reproducibility export | **PASSED** | `aether.cli export` + `verify-export`: 46 hashed inputs (4 ephemeris/EOP + 42 dataset files), lineage re-verified, tamper rejected (`test_export.py`, `test_closed_loop.py`) |
| Offline fallback, clear errors, accessible map alternative | **PASSED** | Coordinate table beside the schematic map; Axe zero serious/critical (§Checks) |
| No NASA endorsement, commanding, measured reduction or blame claims | **PASSED** (review) | README and UI use PRD §22.3 wording; G6 human sign-off pending |
| Measured timing separate from deterministic records; never zero as solver time | **PASSED** | `performance.json` beside `run.json`; `Plan.runtime_s` stays null; the UI shows "unavailable" rather than 0 |

## C. Batch tasks

| Task | Status | Evidence |
|---|---|---|
| DATA-01 | **PASSED** | Commits `2ecbbce` (nullable retrieval), `4ed2109` (Codex-1 code), `b9d7ee9` (sample) |
| DATA-02 | **PASSED** | `643d8c5` (config pin), `033ee98` (lineage, export verification, `--synthetic-only` on benchmark and gate) |
| PERF-01 | **PASSED** | Measured: cold 72 h geometry 385.5 s; warm reference run 107–141 s; adaptive_eig demo run 757 s (612 s in CP-SAT across 47 calls) |
| CAP-01 | **FAILED** (gate); evidence complete | §A G1-F |
| GATE-01 | **FAILED / PENDING DECISION** | §A G4.5 |
| REL-01 | this file; archive in §Checks | |

## D. Out of scope (reviewed in Work_Plan rule 5)

ERA5 replay, Carbon Mapper records, operational tasking and raster flux inversion: **OUT OF SCOPE** for P0.

## Checks

Filled in from the final-revision runs; see the end of `docs/lanes/completion-claude-1.md`.
