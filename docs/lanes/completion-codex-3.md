# Completion batch: Codex-3 status (independent checker and verification)

Worktree: `../AETHER-codex3`  
Branch: `lane/CHK-01-independent-verification`  
Status: checker work complete; integrated-source capacity confirmation remains pending DATA-01/DATA-02.

## Done

- Audited CHK-01..05 against the live checker, planner hand-offs, pinned geometry path, tests, and
  current candidate artifacts.
- Hardened `check_schedule` to reject current-plan selections outside `Plan.candidate_window_ids`,
  before the replan time, or beyond the configured lookahead. It also verifies that option duration,
  window duration, and configured sensor exposure agree.
- Added a replan regression proving a committed acquisition's endpoint geometry is used when
  checking slew for the next plan.
- Added a deterministic capacity-witness script. It uses candidate windows and configuration hashes,
  selects acquisitions without importing solver/policy code, and accepts each insertion only when
  the independent checker reports zero violations.

## Acceptance evidence

| Criterion | Evidence |
|---|---|
| CHK-01 | `tests/unit/test_checker.py`: injected overlap, slew, storage, energy, per-orbit, source-limit, infeasible-window, duration, candidate, time and lookahead cases pass. |
| CHK-02 | Exhaustive oracle test and 500 deterministic CP-SAT comparisons pass; randomized schedules are checked independently. |
| CHK-03 | `tests/unit/test_geometry_cross_validation.py` passes for 20 sampled L4 options using raw SGP4 + Astropy against the 0.05° tolerance. |
| CHK-04 | The 500-instance test reports no invalid CP-SAT or greedy schedules and no oracle objective counterexamples. |
| CHK-05 | Start/end geometry and slew are recomputed by the checker; mutating the orbit slew helper and active greedy alias makes the solver select a schedule that the checker rejects. |
| Committed replans | Unit tests cover committed overlap, committed selection requirements, completed-commitment source-cap release/resource retention, and committed-to-new slew validation. |
| Capacity, current candidate only | The final `scripts/feasibility/capacity_witness.py` run checked 6 feasible groups (58 total window groups existed): `vsat_a:26`=6, `vsat_a:41`=8, `vsat_b:11`=9, `vsat_c:13`=4, `vsat_c:28`=6, `vsat_c:43`=7 acquisitions. All 6/6 final plans were checker-valid; minimum lower bound was 4 per pass. This artifact uses 20 uniform-fill sources (0 plume-seeded) and remains `CANDIDATE_PENDING_AGENT5_REVIEW`; it is not the integrated EMIT source scenario. |

## Checks run

- `pytest -q tests/unit/test_checker.py` — 25 passed after the latest candidate, timing, blackout, and sensor-support changes.
- `pytest -q tests/unit/test_geometry_cross_validation.py` — passed (slow, pinned local data).
- `pytest -q tests/unit/test_truth_isolation.py tests/unit/test_security_baseline.py
  tests/unit/test_import_homes.py` — 47 passed.
- `pytest -q -p no:cacheprovider -rf` — full offline suite passed (288 collected tests).
- `pytest -q tests/unit/test_planner.py tests/unit/test_simulation_science.py tests/integration/test_real_geometry_boundary.py tests/integration/test_examples.py` — passed (exit 0).
- `ruff check .` and `ruff format --check .` in `backend/` — passed (68 files formatted).
- `python scripts/feasibility/capacity_witness.py --output /tmp/aether-codex3-capacity-witness-final.json`
  — completed; emitted `pass_count=6`, `window_group_count=58`, minimum lower bound 4, and 6/6
  passes with at least four checker-validated acquisitions. The report records the candidate
  artifact SHA-256, model/config hashes, source-set hash and source counts.

## Remaining

- Re-run capacity against the immutable Permian manifest and normalized source artifact after
  Codex-1 DATA-01 and Claude-1 DATA-02 are available. The current six-pass witness only verifies the
  synthetic-fill candidate and does not close integrated-source G1-F.
- G2 as a whole still depends on Claude-1's planner integration and merge; this status certifies only
  Codex-3's independent-checker evidence.

Estimated remaining Codex-3 effort after the integrated windows artifact is available: roughly
1–2 active hours for the capacity rerun, full-suite recheck, and final evidence update.
