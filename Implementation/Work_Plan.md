# AETHER — Work Plan

Read first: `AGENTS.md` (rules), `Implementation/Parameter_Register.md` (every number),
`Implementation/PRD_Amendments.md` (where the build departs from the PRD and why),
`Implementation/AETHER_Product_Requirements_Document.md` (requirements),
`Implementation/Parameter_2.md` Parts D–H (security, API, UX, ops, QA rules: adopted as written),
`Implementation/lessons.md` (review findings; closure status in Parameter_Register §0b),
`backend/aether/*/__init__.py` (the interface each lane implements).

## Current completion batch: six-model ownership (supersedes the original lanes below)

This assignment applies to the completion batch described in
`Implementation/Six_Model_Completion_Prompt.md`. It supersedes the original nine-lane
ownership and work sequencing below for this batch. The scientific integrity rules and
acceptance criteria remain binding. Each owner keeps changes in the paths listed here;
cross-owner defects are sent to the owner with a concrete reproducer.

| Owner | Scope for this batch | Coordination boundary |
|---|---|---|
| Claude-1 | Contracts, config, RNG, CLI, runner, configs, root governance and parameter documents, workflow integration, and merges to `main` | Sole owner for shared contracts/config/CLI/runner changes, dataset integration, orchestration, protocol lock, and final evidence matrix. |
| Claude-2 | Sensors, belief, evaluation, experiments, model cards, validation report, and experiment protocol reports | Owns scientific methods, gate analysis, results, and claims; coordinates gate and sign-off with Claude-1. |
| Codex-1 | Ingestion, downloaded/local data, licenses/citations, ingestion tests and docs | Owns EMIT inventory, parser, pinned regional input/manifest, and lineage; requests shared CLI/config changes from Claude-1. |
| Codex-2 | `backend/aether/orbit/`, `scripts/build_orbit_candidate.py`, `docs/orbit-model-report.md`, orbit tests, and window artifact generation | Owns orbit production utilities and G1-F capacity evidence; does not edit checker/oracle or `scripts/feasibility/`. Coordinates independent confirmation with Codex-3. |
| Codex-3 | `backend/aether/planning/checker.py`, `backend/tests/golden/`, `scripts/feasibility/`, checker and geometry cross-validation tests | Owns independent verification; does not implement production orbit or solver fixes. Routes production defects to Codex-2 or Claude-1. |
| Codex-4 | Frontend, backend API, UI/API tests, demo walkthrough, and comparison docs | Owns artifact display and user-facing wording; coordinates result claims with Claude-2 and requests contract changes from Claude-1. |

Use isolated branches/worktrees for the six-model batch. Preserve existing worktrees and
uncommitted changes. Only Claude-1 integrates or merges shared changes. The original
nine-lane plan below is retained as historical context; it is not the active ownership map.

## Status of Wave 0 (done)

Already in the repo and tested (`cd backend && pytest`, 32 passing):

- `configs/`: `base.yaml` (benchmark, no scripted events), `demo.yaml` (extends base, adds the PRD §13.9 cloud event), 4 virtual spacecraft, VS-A sensor, Permian region, 7 scenario families (5 misspecification, 1 resource-scarce, 1 long-horizon).
- `backend/aether/contracts/`: enums and frozen Pydantic models (real plumes and acquisitions, windows with discrete acquisition options, plans, simulated acquisitions without truth fields, beliefs, events, run record).
- `backend/aether/config.py`: typed loader, `extends`, `truth:` overrides, `seed=` override, config hashing, validators (reproducible solver, search step vs minimum window, Markov chain bounds).
- `backend/aether/rng.py`: keyed common-random-number streams derived from one run seed; `derive_seed` for CP-SAT.
- `backend/aether/simulation/truth_types.py`, `planning/context.py`: restricted truth container and the planner-visible context.
- Interface docstrings in every package `__init__.py`.
- Tests: config, contracts, RNG, truth-isolation import guard, checker-independence guard, dangling parameter-ID guard.
- `experiments/protocol.yaml` and seed lists. `scripts/feasibility/pass_budget.py` (independent pass counts).

## Historical lanes and assignment (superseded for the current completion batch)

The Claude lanes get the work that needs cross-cutting judgment: integration, scientific modelling, and claims review. The Codex lanes get modules with crisp specs and test oracles. **Each lane owns its directories exclusively**; anything else goes through the owner (see "Ownership").

| Lane | Agent | Owns | Mission |
|---|---|---|---|
| **L1 Integrator** | Claude-1 | `backend/aether/contracts/`, `config.py`, `rng.py`, `cli.py`, `simulation/runner.py`, `configs/`, `AGENTS.md`, merges to `main` | Keep contracts stable, build the closed loop, own the event log and export bundle |
| **L2 Science model** | Claude-2 | `backend/aether/sensors/`, `backend/aether/belief/`, `docs/model-card-*.md` | Sensor likelihoods, belief filter, EIG |
| **L3 Evaluation & integrity** | Claude-3 | `backend/aether/evaluation/`, `experiments/`, `docs/validation-report.md`, `docs/experiment-protocol.md` | Truth-based metrics, statistics, benchmark runner, wording review of every UI string and README claim |
| **L4 Orbit** | Codex-1 | `backend/aether/orbit/` | SGP4 propagation, windows, rejection reasons, slew helper |
| **L5 Planner** | Codex-2 | `backend/aether/planning/cpsat.py`, `planning/policies.py`, `planning/greedy.py` | CP-SAT model and all five policies |
| **L6 Simulation** | Codex-3 | `backend/aether/simulation/` (except `runner.py`), `backend/aether/weather/` | Truth generator, outcome sampler, synthetic weather |
| **L7 Ingestion** | Codex-4 | `backend/aether/ingestion/`, `data/`, `DATA_LICENSES.md`, `CITATIONS.md` | EMIT V002 adapter, provenance manifest, source placement |
| **L8 Verification** | Codex-5 | `backend/aether/planning/checker.py`, `backend/tests/golden/`, `scripts/feasibility/` | Independent feasibility checker, brute-force oracle, orbit cross-validation |
| **L9 Interface** | Codex-6 | `frontend/`, `backend/aether/api/` | Read-only console over run JSON (PRD §13 screens A–G, P0 subset) |

L8 must not be the same agent as L4 or L5: the checker and the orbit cross-check are only worth having if they're written independently.

## Waves

```
Wave 0 (done) contracts + configs + guards
   │
Wave 1 (parallel, ~1 day)  every lane builds and unit-tests against contracts and its own fixtures
   │     L4 windows ─┐  L2 belief/EIG ─┐  L6 truth/outcomes/weather ─┐  L7 EMIT parser
   │     L5 solver ──┤  L8 checker ────┤  L3 metrics on synthetic RunRecords
   │     L9 UI on example run.json from L1 (INT-02)
   │
Wave 2 (integration, ~1 day)  L1 wires the runner; first end-to-end run; gates G1–G4
   │
Wave 3 (science, ~1 day)  dev-seed tuning → lock protocol → holdout benchmark; demo; G5–G6
```

No lane waits on another lane's code in Wave 1. Wherever you need another lane's output, build a fixture from the contracts. When that lane's real output lands, L1 swaps it in.

## Tasks

Each task: ID, owner, deliverable, **acceptance** (what the PR must show). Turn each into a GitHub issue with that ID in the title. Branch name: `lane/<ID>-short-name`.

### L1 Integrator (Claude-1)

| ID | Deliverable | Acceptance |
|---|---|---|
| INT-01 | Freeze contracts v1: review Wave 0 with all lanes in the first hour, then tag `contracts-v1` | Tag exists. Later contract changes are additive or go through a `contract` PR |
| INT-02 | `docs/examples/run.json`: hand-built, schema-valid example RunRecord (2 policies, 3 plans, 6 acquisitions) | Validates against `RunRecord`; L9 can build every P0 screen from it |
| INT-03 | `simulation/runner.py`: `run_policy(bundle, policy_id, seed)` event loop (see `simulation/__init__.py`) | Integration test: demo m0 seed 1000 runs for 2 policies with 0 checker violations; truth never passed to a policy (isolation test still green) |
| INT-04 | Determinism | Same seed twice → identical `RunRecord` JSON bytes (T-EVAL-02) |
| INT-05 | CLI `windows`, `simulate`, `benchmark`, `export` | Commands from PRD §22.2 work; `export` writes manifest with config hashes, input SHA-256s, package versions |
| INT-06 | Golden demo script `scripts/demo.sh` | Runs PRD §13.9 steps 1–8 end to end offline; forecast injection produces a logged plan revision whose cause is the forecast event |
| INT-07 | CI (`.github/workflows/ci.yml`): ruff + pytest excluding `network`, Python 3.12 and 3.14; actions pinned by SHA, `permissions: contents: read` | Green on `main` |
| INT-08 | Contract hardening | Mutable dict fields replaced by canonical-JSON strings or frozen mappings; runner re-validates every hand-off; test that `model_copy(update={"provenance_class": ...})` is caught at the next boundary |
| INT-09 | Security baseline from Parameter_2 Part D (P0 subset) | `SECURITY.md`; gitleaks + pip-audit in CI; `.env.example`; SEC-IN-007/010 (safe_load only, no pickle) enforced by a lint test; SEC-SPACE-001 denylist check |

### L2 Science model (Claude-2)

| ID | Deliverable | Acceptance |
|---|---|---|
| SCI-01 | `sensors/`: `gsd_effective_m`, `q50_kg_h`, `pod`, `p_valid`, `detection_likelihood` | POD(Q50)=0.5, POD(Q90)=0.9 at reference; monotone in Q (Hypothesis test); POD falls as wind rises; p_valid in [0,1]; cloud 1.0 → p_valid 0 |
| SCI-02 | Sensor model card `docs/model-card-observation.md` | Every parameter maps to a PR-V* ID and tag |
| SCI-03 | `belief/SourceBelief.prior` + `predict` | Tensor sums to 1 within 1e-12; predict with no evidence converges to the regime-mixture stationary p_active; `received_new_evidence=False` |
| SCI-04 | `update` for all four outcomes | INVALID and NOT_OBSERVED leave the tensor bit-identical (PRD §5.6 missingness test); high-POD non-detection drops p_active more than low-POD; matches a hand-computed 2-state fixture to 1e-12 |
| SCI-05 | Detection update with flux | Posterior flux median moves toward the measurement; 90% CI narrows; `flux_ci90_kg_h` ordered |
| SCI-06 | `expected_info_gain_bits` | EIG ≥ 0; EIG = 0 when p_valid = 0; EIG ≤ H(p); matches a Monte Carlo estimate (10⁵ samples, fixed seed) within 0.005 bit |
| SCI-07 | Regime learning check | After 3 detections at 10 h spacing, P(PERSISTENT) rises above its prior |
| SCI-08 | Parameter verification (Register §3–4 [V] items) | Short note in `docs/model-card-source-state.md` with Cusworth 2021 paper values and the EMIT-fixture flux comparison |
| SCI-09 | `expected_brier_reduction` utility (PR-O10 ablation) | Closed form on the grid; equals a Monte Carlo estimate within 0.005; is ~0 for an episodic-regime belief when the next pass is > 12 h away |
| SCI-10 | Consistency tests | Unit invariance (all fluxes ×3600 → identical p_active); m0 calibration on 5 dev seeds: 90% flux intervals cover 0.85–0.95 and the reliability curve is within sampling error |

### L3 Evaluation & integrity (Claude-3)

| ID | Deliverable | Acceptance |
|---|---|---|
| EVL-01 | `evaluation/metrics.py`: all metrics in `protocol.yaml` | Each metric has a hand-computed unit test on a 2-source, 12-hour synthetic RunRecord + TruthHistory |
| EVL-02 | Corroboration with right-censoring | Never-corroborated sources reported as censored, not dropped |
| EVL-03 | `paired_bootstrap` | Seeded and reproducible; CI contains the true difference on a synthetic known-effect test about 95% of the time (200 trials) |
| EVL-04 | `benchmark()` writes `benchmark-results.csv`, `benchmark-confidence-intervals.json` | Per family × policy × regime; includes denominators and checker-violation counts |
| EVL-05 | Protocol lock procedure | `protocol.yaml` `locked: true` committed and tagged before any holdout seed runs; script refuses holdout seeds if unlocked |
| EVL-06 | Integrity review | Every UI string and README claim checked against the PRD §22.3 allowed-wording table; issues filed against L9/L1 |
| EVL-07 | `docs/validation-report.md` | Results for all families including negative ones; no "X% better" without CI |
| EVL-08 | `evaluation/reference.py`: `OraclePolicy` (reads truth) + `discriminability_gate()` | On dev seeds reports oracle−random Brier gap, its SD, capacity/demand ratio and passes/acquisitions per pass; G4.5 verdict written to the validation report |

### L4 Orbit (Codex-1)

| ID | Deliverable | Acceptance |
|---|---|---|
| ORB-01 | `build_satellite(profile)` via `Satrec.sgp4init` | Propagated altitude 500 ± 5 km; period 94.62 ± 0.05 min; SGP4 error codes raise |
| ORB-02 | LTDN check | Test asserts each plane's descending-node local solar time matches `ltdn` within ±2 min on day 1 |
| ORB-03 | `generate_windows` with 2 s search, refinement and AcquisitionOptions | Overhead target gives a window containing off-nadir ≈ 0; target 2000 km off-track gives NOT_VISIBLE/POINTING; night target gives DARK; boundaries refined to ≤ 0.1 s; a hand-placed edge-of-field target with a ~12 s window is found; each option's LOS is computed at its own start time |
| ORB-04 | `slew_time_s(option_a, option_b, attitude)` for solver and greedy | 0° → settle only; 30° at 1.5°/s → 20 s + settle. Not used by the checker |
| ORB-05 | Pass-budget report `docs/orbit-model-report.md` | Reproduces `scripts/feasibility/pass_budget.py` counts within ±1 pass; reports acquisitions-per-pass capacity (Gate G1-F) |
| ORB-06 | Publish `backend/tests/golden/windows_base.json` | Windows for `base.yaml`, 72 h, 20 sources (seeded placement), with options; consumed by L5/L8 tests |
| ORB-07 | `load_ephemeris()` from pinned `data/ephemeris/de421.bsp` + SHA-256 manifest; `scripts/fetch_ephemeris.sh` | Network-disabled test run gives identical windows; `pass_budget.py` uses the pinned file |

### L5 Planner (Codex-2)

| ID | Deliverable | Acceptance |
|---|---|---|
| PLN-01 | `cpsat.solve_schedule`: one Boolean per option, ≤ 1 option per window, exact pairwise slew exclusions, NoOverlap per sat | On ≤ 12-option instances, objective equals L8's brute-force oracle on 200 random instances |
| PLN-02 | Per-source visit limit, per-orbit count, cumulative storage/energy | r1 family: no plan exceeds storage; zero-candidate input returns empty plan with status OPTIMAL |
| PLN-03 | Status and statistics | OPTIMAL/FEASIBLE/UNKNOWN mapped; bound and runtime recorded; `max_deterministic_time`, `num_workers=1`, `derive_seed` from config/rng; same input twice → identical plan |
| PLN-04 | `greedy.py` shared greedy insertion | Uses `orbit.slew_time_s`; never produces a plan L8 rejects (property test) |
| PLN-05 | Policies in `policies.py`: the five competitors + `random_feasible` | Same inputs → each policy deterministic; `static_priority` utilities frozen at revision 0; `first_feasible` serves the PR-E07 request stream in arrival order |
| PLN-06 | Explanations | For every rejected candidate, reason in {`INFEASIBLE`, `LOW_GAIN`, `CONFLICT`, `SOURCE_LIMIT`, `BUDGET`} (PRD FR-OPT-006) |

### L6 Simulation (Codex-3)

| ID | Deliverable | Acceptance |
|---|---|---|
| SIM-01 | `weather/synthetic.py` `WeatherModel` | Empirical mean cloud within 0.02 of config over 10⁴ draws; spatial correlation at 150 km ≈ e⁻¹ ± 0.1; forecast error grows with lead time |
| SIM-02 | ERA5 check script (network-marked) | Computes Oct Permian mean total cloud cover and 10 m wind median; results noted in Register PR-W01/W10 |
| SIM-03 | `truth.generate_truth` | Empirical regime frequencies and stationary fractions match config within 3σ over 10⁴ sources; reproducible by seed |
| SIM-04 | `outcomes.sample_outcome` | Detection frequency matches POD × p_valid within 3σ (10⁵ draws); INVALID when cloud = 1; same (source, sensor, minute) → same draws for two different policies |
| SIM-05 | Injected events | Forecast revision appears in both truth and forecast at `at_hour` |
| SIM-06 | Leakage guard extension | Test proves `WeatherModel` objects given to the runner's planner side expose only forecast methods (wrapper or protocol split) |

### L7 Ingestion (Codex-4)

| ID | Deliverable | Acceptance |
|---|---|---|
| ING-01 | Synthetic EMIT-shaped fixture `data/fixtures/emit_v002_synthetic.geojson`, labelled `EXAMPLE_ONLY_NOT_SOURCE_VERIFIED` | Parser tests run offline; contains an `N/A` rate, a missing uncertainty and a malformed polygon |
| ING-02 | `parse_emit_plume_geojson` against **real** V002 granules (needs Earthdata login) | 10–20 real Permian plumes pinned in `data/manifests/emit_permian.json` with SHA-256, URL, retrieval time; real field names documented |
| ING-03 | Validation diagnostics | Malformed rows rejected with per-row reason; `N/A` → `None` + `missing_rate_reason` |
| ING-04 | `cluster_to_sources` | 500 m clustering; `seeded_from_plume_id` set; deterministic |
| ING-05 | `DATA_LICENSES.md`, `CITATIONS.md` | Every dataset in use has license URL, attribution text and redistribution status |
| ING-06 | Carbon Mapper terms record (P1 adapter optional) | Terms URL and version recorded before any record is stored |

### L8 Verification (Codex-5)

| ID | Deliverable | Acceptance |
|---|---|---|
| CHK-01 | `planning/checker.py` independent checker | Detects each injected violation type (overlap, slew, storage, energy, per-orbit count, source limit, infeasible window) on hand-built plans; imports nothing from `cpsat`/`policies` (guard test exists) |
| CHK-02 | Brute-force oracle `tests/golden/oracle.py` | Exhaustive optimum for ≤ 12 windows; used by PLN-01 |
| CHK-03 | Orbit cross-validation | For 20 sampled options, off-nadir and sun elevation recomputed with raw `sgp4` + Astropy agree with L4 within 0.05° |
| CHK-05 | Checker recomputes LOS and slew itself | Checker uses its own propagation at each option's start/end. Mutation test: monkeypatching `orbit.slew_time_s` to return 0 makes the solver emit a plan the checker rejects |
| CHK-04 | Property tests | Random plans from greedy and CP-SAT on 500 random instances: 0 checker violations |

### L9 Interface (Codex-6)

| ID | Deliverable | Acceptance |
|---|---|---|
| UI-01 | Vite + React + TypeScript app reading `docs/examples/run.json` | Builds offline; TypeScript types generated from or hand-matched to `RunRecord` |
| UI-02 | Screen A Overview + **SIMULATED MISSION** banner; Screen C windows Gantt per satellite | Rejected windows show reasons; every simulated element is labelled |
| UI-03 | Screen D source panel: P(active) over time with evidence markers by outcome type | INVALID/NOT_OBSERVED visibly distinct from non-detection; "insufficient evidence" text where applicable |
| UI-04 | Screen E planner: utilities table, selected windows, before/after on replan with cause | Reads plan revisions; no client-side recomputation |
| UI-05 | Screen F comparison from `benchmark-results.csv` | Shows CIs and seed counts; "insufficient samples" when n < 10 |
| UI-06 | Accessibility | Keyboard navigation; table alternative for every chart and map; colour never the only cue; axe in Playwright with 0 serious violations (UX-A11Y-006) |
| UI-08 | Apply Parameter_2 Part F | Design tokens UX-TOK, provenance encoding UX-PROV (colour + line style + text tag), number rules UX-NUM, copy lint UX-COPY-003 in CI |
| UI-07 | `api/` FastAPI read-only server over `runs/` (P0 optional) | `GET /runs`, `/runs/{id}`, `/runs/{id}/windows`, `/runs/{id}/plans` |

## Gates (PRD §3.4, made concrete)

| Gate | Passes when | Checked by |
|---|---|---|
| G0 Data | ING-01, ING-03 merged (ING-02 when credentials exist) | L3 |
| G1 Orbit | ORB-01..05 + CHK-03 merged; G1-F pass budget ≥ 5 passes/72 h and ≥ 4 acquisitions/pass | L8 |
| G2 Planner | PLN-01..04 + CHK-01, CHK-02, CHK-04 merged | L8 |
| G3 Inference | SCI-03..06 merged | L3 |
| G4 Feedback | INT-03, INT-04, SIM-05: forecast injection (demo.yaml) changes a plan with logged cause | L3 |
| **G4.5 Discriminability** | EVL-08 on dev seeds: oracle−random gap > 2 × SD; capacity/demand reported. If it fails, resize the scenario (`h168`, more sources, tighter capacity). Never tune the planner to pass it | L3 + human |
| G5 Science | EVL-04, EVL-05: holdout benchmark run on locked protocol | L1 + human |
| G6 Demo | INT-06, UI-02..05, EVL-06 | human |

## Ownership and coordination rules

1. **Contracts are owned by L1.** Need a new field? Open a PR touching only `contracts/` + tests, tagged `contract`. L1 merges within the hour or replies. Never redefine a contract type locally.
2. **Never edit another lane's directory.** If you find a bug there, file an issue with a failing test attached.
3. **Shared helpers have a single owner.** `orbit.slew_time_s` (L4) and `sensors.*` (L2) are called by the solver, policies, simulator and belief, and reimplemented by no one. The exception is L8's checker, which must **not** call them. It re-derives geometry and slew on purpose.
4. **Small PRs, rebased on `main`, green tests.** L1 merges. Run `pytest` and `ruff check` before opening a PR.
5. **Numbers come from the register.** A new constant needs a PR-ID row in `Parameter_Register.md` in the same PR.
6. **Status:** each lane keeps `docs/lanes/<LANE>.md` (owned by that lane only) with done/doing/blocked. This avoids a shared status file that everyone conflicts on.

## Critical path

`INT-01 → (ORB-03, SCI-04, SIM-04, PLN-01, CHK-01 in parallel) → INT-03 → INT-04 → EVL-08 (G4.5) → EVL-05 lock → EVL-04 → G5`.
The slowest items are probably ORB-03 (window refinement) and PLN-01 (slew modelling). Start them first.
