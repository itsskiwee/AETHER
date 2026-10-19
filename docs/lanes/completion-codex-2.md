# Codex-2 completion status — orbit and capacity

**Date:** 2026-10-18  
**Branch:** `lane/ORB-05-capacity-closure`

## Scope and changes

- Recorded the superseding six-model ownership map in `Implementation/Work_Plan.md` before code
  changes.
- Extended `scripts/build_orbit_candidate.py` to measure per-pass capacity with the production
  CP-SAT schedule model, record local checker results and code/input hashes, and refresh capacity
  from serialized windows without repeating orbital propagation.
- Added a capacity constraint test and a deterministic pinned-ephemeris window replay test.
- Generated `data/fixtures/windows_base_candidate.json` and
  `data/fixtures/windows_permian_sample_candidate.json`.
- Updated `docs/orbit-model-report.md` with orbit acceptance evidence, capacity results, lineage
  and limitations.

No production orbit, checker, solver, scenario parameter, config or golden fixture was changed.

## Acceptance evidence

- ORB-01..04 checks cover configured altitude/period and SGP4 errors, LTDN, LOS/window geometry,
  boundary refinement, exposure-time LOS and slew/settling. The offline replay test confirms
  identical output from the pinned ephemeris and fails if address validation is reached.
- ORB-05 synthetic base result: six passes with feasible selected-source windows and 5–10
  schedule-constrained acquisitions per pass. All solves are `OPTIMAL`; the independent checker
  reports zero violations. Codex-3 independently reconstructed and reoptimized all six schedules.
- ORB-05 historical-location sample: seven passes with feasible windows, but one has only two
  acquisitions. This **fails** the registered ≥4 capacity threshold. No parameters were changed.
  Codex-3 independently checked all seven schedules, reproduced the counts and confirmed zero
  violations.
- ORB-07: both candidate artifacts record verified DE421 and IERS input hashes, config and code
  hashes, software versions and source-set identity. The real-location artifact also records hashes
  for 20 selected metadata files and 20 raster files; only ID, acquisition time and coordinates
  were used for source placement.
- ORB-06 golden promotion remains with Codex-3. Both candidates remain pending and neither is
  written into `backend/tests/golden/`.

The per-pass optimizations are independent. Cross-pass resource carryover is not modeled, so
acquisition counts must not be summed into a 72-hour throughput claim.

## Checks

- `pytest -q tests/unit/test_orbit_engine.py tests/unit/test_geometry_cross_validation.py tests/unit/test_orbit_capacity.py` — **14 passed**, exit 0.
- `pytest -q tests/unit/test_orbit_capacity.py` rerun after the final metadata-status update — **1 passed**.
- Ruff check and format check passed for owned Python files.
- `git diff --check` passed.
- Codex-3 verified both final candidate hashes and their source lineage after the status/hash
  refresh. It reconstructed and checked all 13 schedules; every checker run had zero violations,
  and independent OPTIMAL reruns reproduced all stored counts.

No repository-wide test result is claimed.

## Remaining dependencies

- Codex-1's normalized dataset manifest and shared contract integration are still pending. The
  inventory retrieval time and source URL are unknown, and are recorded as unknown.
- The selected historical-location source geometry fails G1-F capacity. This result is preserved
  for scientific review; changing scenario parameters is outside this lane.
- Codex-3 owns any golden-window promotion and final verification.

**Codex-2 implementation remaining:** none. Completion of integrated-source acceptance depends on
the owners above; their timing is not estimated here.
