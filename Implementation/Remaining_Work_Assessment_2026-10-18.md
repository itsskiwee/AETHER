# Remaining work assessment — 18 October 2026

Scope: amended AETHER P0 research prototype, using the local EMIT download. This assessment reads implementation documents, current source, and existing evidence; it does not re-run tests or benchmarks. The working tree was clean before these two planning documents were added. Completion percentages below are judgment estimates, not task-count measurements.

## Current position

The offline demo is delivered. The implementation is approximately 80–90% complete as software, and 65–75% complete as an evidence-backed P0 research delivery. Roughly 25–35% of the overall delivery effort remains, concentrated in real-data integration and scientific acceptance. P1 extensions are outside this estimate.

Evidence: `docs/validation-report.md`, `docs/lanes/L1.md`, `docs/lanes/L3.md`, `docs/lanes/L9.md`, `runs/demo/acceptance.json`, and current CLI/runner/benchmark source. Existing reports record 294 backend tests, 13 browser tests, deterministic demo replay, export reloads, and zero demo checker violations. Those are previously recorded results, not a fresh verification in this assessment. Older lane notes contain superseded blockers and “uncommitted” labels; do not treat these as current solely because they remain in a status file.

## What was downloaded

Local directory: `data/raw/EMITL2BCH4PLM_002-20261018_042728/`.

- 1,686 JSON metadata files and 1,686 TIFF files; every metadata filename has a matching TIFF filename.
- 118,509,938 bytes across the raw files (about 113 MiB); the additional raw-directory file is an empty `.gitkeep`.
- All 1,686 JSON documents decoded successfully during inventory. This is not raster integrity verification or full contract validation.
- Observations span 2022-08-10 through 2025-09-22 and cover multiple regions globally.
- 155 metadata records, with 155 distinct plume IDs, are inside the configured Permian bounding box [-104.5, 30.8, -101.0, 33.5]. 73 of those records have numeric emission-rate estimates. Spatially distinct source count after 500 m clustering remains to be measured.
- Across the complete download, 596 records have numeric emission-rate estimates and 1,090 use `NA`.
- Actual metadata keys include `Plume ID`, `UTC Time Observed`, `Latitude of max concentration`, `Longitude of max concentration`, `Emissions Rate Estimate (kg/hr)`, and `Emissions Rate Estimate Uncertainty (kg/hr)`.

The current parser expects different key names. Its comment and `docs/ingestion-adapters.md` also incorrectly generalize that native metadata lacks kg/h estimates. Correct this from the downloaded evidence, preserve `NA`, and establish uncertainty semantics before assigning a statistical interpretation. The presence of a numeric uncertainty does not prove it is a standard deviation.

There is no local ERA5 dataset under project `data/`; only synthetic weather code is present. Carbon Mapper data are not present there. Neither is a P0 prerequisite under the recorded scope. No further EMIT download is required to begin ING-02, although authentic provider URLs/retrieval evidence still need to be recovered or explicitly marked unavailable.

## Remaining work and effort

These estimates are active engineering/review hours summed across agents. They are not measured model speeds.

| Work package | Current gap / acceptance | Owner in six-agent plan | Active hours |
|---|---|---|---:|
| Real EMIT ingestion | Actual field aliases, diagnostic inventory, null/units handling, deduplication, TIFF pairing/integrity checks, 10–20 representative Permian records pinned by manifest, provenance and licenses | Codex-1 | 6–10 |
| Runner/CLI/export integration | Runner accepts plume inputs, but CLI simulate/windows and default benchmark currently provide none. Add explicit pinned dataset input throughout; hash it; record real-seeded versus synthetic-fill counts | Claude-1 | 8–14 |
| Scientific calibration and review | SCI-08 real-flux comparison, SCI-10 multi-seed calibration, registered assumptions, uncertainty interpretation, m0 persistence caveat | Claude-2 | 8–14 |
| Orbit/capacity closure | Establish G1-F ≥5 passes/72 h and ≥4 feasible acquisitions/pass with actual geometry; audit remaining ORB acceptance and golden artifact | Codex-2 | 4–8 |
| Independent verification | Audit checker/committed selections and outstanding task criteria; validate changed source placement, provenance boundaries and replay independently | Codex-3 | 6–10 |
| Benchmark preparation and analysis | G4.5 on 30 development seeds, power calculation, lock procedure, all-family aggregation and honest positive/negative report | Claude-2 | 8–14 |
| Runtime measurement | `runner.py` nulls Plan runtime; p95 metric currently depends on Plan runtime. Add separate measured performance artifact without breaking deterministic RunRecord bytes | Claude-1 | 3–5 |
| Console/documentation acceptance | Display real historical context and provenance; show final sample counts/CIs/verdict; refresh obsolete blockers; complete P0 traceability and final packaging | Codex-4 | 5–9 |
| Integration review and fixes | Merge coordination, complete required checks, resolve cross-package regressions, final evidence table | Claude-1 with independent review | 6–10 |
| **Total** | Excludes unattended benchmark execution and external scientific review | | **54–94** |

Practical elapsed estimate with two large Claude and four small Codex sessions: **3–5 working days**, assuming all six can run concurrently, existing behavior largely holds, G4.5 passes, and benchmark compute fits overnight batches. A focused data-backed demo refresh could take **one working day**; full scientific acceptance is a larger deliverable. Allow **5–8+ working days** if calibration or G4.5 fails, data defects are extensive, or benchmark execution dominates. These are planning ranges, not guarantees.

Compute is the largest unmeasured variable. Six benchmark families × five policies × 30 development seeds = 900 runs for a complete competitor development matrix. A G4.5 reference pair adds 60 runs per family evaluated. At the default upper budget of 100 holdout seeds, the holdout matrix is 3,000 runs. Determine the actual required seed count using tuning SD and the approved 0.01 Brier-point minimum effect. Do not silently cap a power requirement at 100 and claim adequate power.

Measure representative development runs after data wiring. Estimate compute as Σ(number of runs in each family/policy × measured mean runtime) / measured effective worker throughput, with additional allowance for long horizons, CP-SAT tails, retries, and independent checks. For illustration only, 3,000 runs averaging 60 seconds take 50 CPU-worker hours, or at least 8.3 wall hours at effective throughput of six workers; averaging ten minutes gives 500 worker hours, at least 83 wall hours at that throughput. Six coding sessions do not establish six available simulation workers. Do not start holdout just to measure runtime.

## Order and decision points

1. In parallel: actual-schema ingestion; orbit capacity audit; independent checker audit; scientific review; UI/documentation preparation. Claude-1 freezes the new six-agent ownership map and prepares dataset wiring.
2. Integrate the pinned Permian input and recheck deterministic source construction, export hashes, provenance, and same-input fairness across policies. Historical detections seed geography/context; they do not become simulated ground truth or contemporaneous 2026 observations.
3. Finish calibration, capacity evidence, and 30-seed G4.5. If G4.5 fails, report it and propose a registered scenario revision; Work_Plan requires human participation at that gate. Never tune the planner to manufacture a pass.
4. Estimate power and compute; review and commit/tag the locked protocol before any holdout execution. Preserve existing human sign-off requirements at G5/G6. Protocol lock must bind the exact dataset manifest and code revision.
5. Run the agreed holdout matrix, report every family and comparator, complete checks, and package the data-backed demo and research evidence. A negative result can complete the experiment; a successful performance claim requires the registered criterion.

Publication additionally requires the domain review recorded in Parameter_Register §10. Downloaded plume estimates cannot establish operational sensor performance, persistence calibration, or real-world methane reduction.

## Deliverable

Use `Implementation/Six_Model_Completion_Prompt.md` as the coordinating prompt and copy the role-specific section to each model. It explicitly replaces the old nine-agent assignment for this completion batch while preserving scientific boundaries and checker independence.
