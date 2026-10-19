# AETHER completion handoff — two large Claude models + four small Codex models

## Master prompt (give to Claude-1)

You are coordinating completion of AETHER in `/home/itsskiweee/Projects/AETHER` with exactly two large Claude sessions and four small Codex sessions. Complete the remaining amended P0 work using the datasets already downloaded. Preserve the delivered demo. Read `AGENTS.md`, `CLAUDE.md`, `Implementation/Work_Plan.md`, `Implementation/PRD_Amendments.md`, `Implementation/Parameter_Register.md`, relevant PRD sections, Parameter_2 Parts D–H, package interface docstrings, current validation/model cards, and `Implementation/Remaining_Work_Assessment_2026-10-18.md`.

The user requests a six-model split. Before code edits, record the batch ownership map below as a superseding assignment in Work_Plan; original scientific rules remain binding. Do not restart the original nine-lane build. Inspect actual source and artifacts before treating old “blocked/uncommitted” notes as current. Preserve other sessions' edits. Coordinate separate branches/worktrees and small reviewed changes. Only Claude-1 merges or changes shared contracts/config/CLI/runner. Nobody edits another role's files; send a concrete issue and failing example to the owner.

Local data: `data/raw/EMITL2BCH4PLM_002-20261018_042728/`, containing 1,686 metadata JSONs and matching TIFFs. Current inventory finds 155 unique plume records inside the configured Permian bbox, 73 with numeric kg/hr rates. Actual keys use spaces: `Plume ID`, `UTC Time Observed`, `Latitude of max concentration`, `Longitude of max concentration`, `Emissions Rate Estimate (kg/hr)`, `Emissions Rate Estimate Uncertainty (kg/hr)`. Recompute counts and validate content; do not assume current parser aliases work. Most globally downloaded records are outside the study region. Use existing inputs first. Missing authentic provenance metadata must be reported honestly, never fabricated from filenames or filesystem timestamps.

Existing evidence records an accepted offline demo, 294 backend tests, 13 browser tests, six preliminary competitor runs on two m0 seeds, unlocked protocol, no G4.5 result, and no holdout. Revalidate after changes. The end goal is a reproducible data-backed P0 prototype and completed, honestly reported scientific experiment, including negative results where applicable.

## Ownership and role prompts

### Claude-1 (large): integration, contracts, execution and release

Own original L1 scope: contracts, config, rng, CLI, runner, configs, root governance/parameter documents, workflow integration and merges. Coordinate new status files `docs/lanes/completion-claude-1.md` etc. You own the final P0 requirements-to-evidence matrix and run orchestration; Claude-2 owns methods/results.

1. Agree an explicit immutable dataset-manifest interface with Codex-1 and Claude-2. Wire local ingestion into `windows`, `simulate`, and default benchmark execution. `run_policy` already accepts plume observations; current default callers omit them. Make dataset selection reproducible and visible. Preserve a documented synthetic-only mode and report uniform fill explicitly. An explicitly requested missing/invalid real dataset must fail clearly rather than quietly falling back.
2. Source selection must be deterministic, regional, deduplicated and policy-independent. Share the same manifest and source construction for comparisons. Export hashes for raw selected inputs, normalized inputs, manifests, transformations, configs and code. Do not read every global raster in the simulation loop.
3. Historical 2022–2025 observations are context/location evidence for the virtual scenario at its configured epoch. Keep REAL_OBSERVATION, MODEL_INFERENCE, SIMULATED_OBSERVATION and SIMULATED_GROUND_TRUTH separate. Do not set truth from downloaded rates or use historical detections to claim present activity. Any prior-fitting proposal needs Claude-2 review and an explicit protocol/parameter change.
4. Add genuine timing measurements in a separate performance artifact; preserve identical deterministic RunRecord bytes. Coordinate evaluation and frontend consumers. Never represent zero as a measured solver runtime.
5. Run development pilots only after integration; record machine/worker throughput and forecast the full benchmark cost. Orchestrate G4.5 with Claude-2, then protocol commit/tag and holdout under existing gate rules. Obtain required human participation for scenario changes at G4.5 and G5/G6 sign-off; do all reviewable work first.
6. Ensure protocol lock binds dataset/config/code identity. Reproduce checksums, replay, export reloads, integration, lint/security and browser acceptance. Package final evidence; do not publish, push or send external messages without existing authorization.

### Claude-2 (large): scientific models, evaluation and research integrity

Own original L2 + L3: sensors, belief, evaluation, experiments, model cards, validation and experiment protocol reports. Keep responsibilities explicit: Codex-3 independently audits feasibility; you review scientific methods and reporting.

1. Review actual EMIT fields with Codex-1. Verify units and uncertainty meaning from provider documentation. Numeric rate uncertainty stays UNKNOWN unless its definition supports a stronger interpretation. Compare usable historical fluxes with the registered prior (SCI-08), reporting selection/missingness bias. Do not claim detection-selected plume rates validate a population prior or infer persistence from absent plume rows.
2. Complete SCI-10 multi-seed m0 calibration and remaining scientific criteria against meaningful oracles. Retain approved unverified persistence assumptions and 0.01 Brier-point minimum effect unless an explicit decision changes them; propose choices with evidence rather than silently changing assumptions.
3. Evaluate G4.5 on the 30 development seeds, with oracle-informed greedy versus random references, paired SD (not SE), capacity/demand, passes and feasible acquisitions/pass. Do not describe the greedy reference as a proven upper bound. Establish and document the family scope of the gate before running it. On failure, report and recommend a scenario adjustment for review; never tune the planner to pass the gate.
4. Calculate required holdout sample count using observed paired tuning SD and the registered power rule. Document requirements exceeding the default 100-seed budget and resolve before lock. Verify no holdout leakage. Lock/commit/tag through Claude-1 before any holdout run.
5. Produce all six registered family results for five competitor policies, primary adaptive-vs-largest comparison, equally prominent adaptive-vs-greedy, CIs, multiplicity correction, seed counts, denominators, censoring and zero-checker-violation evidence. Keep reference policies distinct. Coordinate separate timing artifact ingestion with Claude-1. Report missing timing honestly.
6. Update model cards and validation report, including failed hypotheses and unresolved domain review. Review every changed claim/UI string. A negative registered result is a valid completed experiment; do not promise an adaptive win.

### Codex-1 (small): bounded ingestion and local dataset preparation

Own original L7: `backend/aether/ingestion/`, `data/`, `DATA_LICENSES.md`, `CITATIONS.md`, ingestion documentation and ingestion tests. Request shared config/CLI changes from Claude-1.

1. Inventory the full local download and matching TIFFs; verify file integrity using appropriate local tools, regional coverage, duplicate IDs and missing values. Do not perform methane inversion from rasters; P0 uses provider estimates. Retain raw inputs untouched.
2. Extend parser aliases for the exact observed keys, including real ID, UTC timestamp, representative coordinates, rates and uncertainties. Preserve raw properties and geometry. kg/hr is numerically kg/h. Never confuse enhancement ppm·m with emissions kg/h. Preserve `NA` as null with an appropriate reason. Keep uncertainty kind conservative pending Claude-2 review.
3. Generate deterministic accepted/rejected diagnostics, a full local inventory, and a pinned 10–20-record representative Permian manifest (include numeric/missing cases). Record actual hashes, provider identity/version, source URLs and authentic retrieval evidence where available. Flag unknowns. Respect redistribution rules; keep bulk raw files out of git.
4. Export a deterministic normalized regional input and manifest for Claude-1; quantify 500 m clustered source count. Capture complete input lineage. Test actual-schema fixtures, source identity/hash checks, malformed cases, null semantics, duplicates and order invariance. Correct adapter docs that claim these downloaded native metadata never contain kg/h fields.

### Codex-2 (small): orbit and capacity closure

Own original L4 plus orbit-production utilities: `backend/aether/orbit/`, `scripts/build_orbit_candidate.py`, `docs/orbit-model-report.md`, orbit-specific tests and window artifact generation. Do not edit checker/oracle or independent `scripts/feasibility/`.

Audit ORB-01..07 against current evidence. Confirm pinned DE421/EOP and offline reproducibility; close altitude/period/LTDN/window refinement and option-start/end geometry criteria. Measure feasible acquisitions per pass using actual windows and scheduling constraints, alongside pass counts, for the integrated source scenario. Coordinate independent confirmation with Codex-3. Supply G1-F evidence for ≥5 passes/72 h and ≥4 feasible acquisitions/pass; counts of candidate options alone do not establish capacity. Publish/reconcile the named golden-window artifact through its verification owner. Report failures rather than altering registered scenario numbers independently.

### Codex-3 (small): independent checker and verification

Own original L8: `backend/aether/planning/checker.py`, `backend/tests/golden/`, `scripts/feasibility/`, checker and geometry cross-validation tests. Audit planner behavior independently; request planner fixes from Claude-1, who temporarily owns production planner files for this batch. Do not implement production orbit or solver fixes yourself.

Audit CHK-01..05 and G2 evidence, especially validation against committed acquisitions across replans. Independently check injected overlap/slew/energy/storage/source-limit violations, brute-force solver agreement, mutation sensitivity and geometry cross-validation. Independently confirm capacity evidence. After real-source wiring, verify replay, policy input fairness, zero checker violations, source/manifest lineage and no truth leakage; route fixes to owning roles. Use actual acceptance criteria, not only happy-path runs. Never import planner policies/solver into the checker or call production slew helpers. Record exactly what you verified and remaining counterexamples.

### Codex-4 (small): console, artifact display and final documentation

Own original L9: frontend, backend API, UI/API tests, demo walkthrough and comparison docs. Coordinate claims with Claude-2; request contract changes from Claude-1.

Expose historical EMIT context with provenance, observation dates, source lineage, null flux and uncertainty semantics. Label virtual acquisitions as simulated. Make seeded locations and synthetic fills understandable. Display new benchmark CIs, sample counts, family coverage, preliminary/locked status and genuine timing when available; provide honest unavailable states. Keep authoritative values in artifacts, never calculate replacement scientific results in the browser. Rehearse keyboard/table alternatives, copy, accessibility and actual API artifact replay. Update walkthroughs and remove obsolete data-download blockers in owned documents. Deliver a usable demo with actual pinned dataset evidence, plus clear limits on research conclusions.

## Sequencing and finish criteria

Wave A: Claude-1 records ownership and prepares interfaces; Codex-1 inventories/adapts data; Claude-2 reviews semantics/calibration; Codex-2 audits orbit; Codex-3 independently audits checker; Codex-4 prepares artifact display.

Wave B: integrate one immutable regional dataset; run deterministic data-backed development pilots; fix owner-routed defects; complete calibration and capacity; measure runtime/throughput; run the planned 30-seed discriminability gate.

Wave C: resolve gate decisions, calculate power, prepare a concrete protocol/dataset/code freeze, obtain required scientific sign-off, commit/tag lock, then run holdout. Keep all pre-lock runs development-only. Never reuse the two-seed demo comparison as scientific acceptance.

Wave D: independent review, all registered results, refreshed claims, complete required tests/lint/security/build/browser checks, final archive/manifests and requirements evidence table. Separate completed implementation, completed experiment, passed scientific gates and external publication review in final reporting.

Each role must report changed files, acceptance criteria met, exact checks/results, evidence paths, unresolved blockers and estimated remaining effort. Finish only when every P0 requirement has evidence or an explicit reviewed scope decision. Do not expand into ERA5 replay, Carbon Mapper, operational tasking, full deployment or raster flux inversion unless separately requested.
