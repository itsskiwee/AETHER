# AETHER — PRD Amendments (A1)

**Date:** 17 Oct 2026 · **Amends:** `AETHER_Product_Requirements_Document.md` v1.0
**Why:** the build departs from the PRD in places, mostly for reasons found while sizing the experiment (see `lessons.md` §1.3). This file keeps the PRD authoritative: where an amendment and the PRD disagree, **the amendment wins**. Numbers live in `Parameter_Register.md`, and this file cites their IDs rather than restating them.

| # | PRD section | Original | Amended | Reason |
|---|---|---|---|---|
| A1-01 | §3.1, §9.1 P0 scope | 1–2 virtual satellites | **4** virtual satellites in 2 sun-synchronous planes | Computed pass budget: 2 satellites give 3 regional passes in 72 h, too few decisions to test adaptivity (Register §1). |
| A1-02 | §3.1, §7.5 policies | ≥ 2 in P0 | 5 competitors (B1–B4 + `greedy_eig`) plus 2 reference policies (`random_feasible`, `oracle`) | `greedy_eig` separates adaptivity from the optimizer. The reference policies power gate G4.5. P0 primary comparison stays `largest_first` vs `adaptive_eig`. |
| A1-03 | FR-SIM-008 | Misspecification families are P1 | **P0** (`configs/scenarios/m1–m4`) | Without them, the planner and simulator share one model and an adaptive "win" is circular. |
| A1-04 | §3.4 gates | G0–G6 | Add **G4.5 Discriminability** (oracle − random Brier gap > 2 × SD on dev seeds; capacity/demand reported) and an **m0 calibration** condition in G3 | A benchmark that cannot separate the bounds cannot separate the policies (`lessons.md` §2.1). |
| A1-05 | §5.4 source state | Single 2-state Markov chain | 3-regime mixture: static latent regime, per-regime 2-state chain, static flux plus hourly variability (PR-P10–P23) | Anchored to Permian intermittency [S16]. Observations reveal regime as well as state. |
| A1-06 | §5.5–5.6 likelihood | Qualitative | One detection definition (PR-V22); false-alarm flux density (PR-V21); σ_eff (PR-V41); belief uses estimated wind (PR-W13), never true wind | Unit-invariant posteriors; a well-specified m0; no truth leakage through environment fields. |
| A1-07 | §7.1–7.2 objective | One-step binary EIG | Default unchanged. Add ablation `brier_reduction_to_next_pass` (PR-O10) | One-step EIG ignores information decay between pass clusters ~21 h apart. |
| A1-08 | §7.3 constraints, §20 granularity | Variable start inside window | Discrete **AcquisitionOptions** every 10 s (PR-O09). Slew is an exact pairwise exclusion between options | Makes slew exact and independently checkable. |
| A1-09 | FR-ORB-007, §17 | Independent checker | The checker recomputes LOS and slew with its own propagation, never calls `orbit.slew_time_s`; mutation test required | A shared helper bug would otherwise pass both solver and checker. |
| A1-10 | §6 pass search | Unspecified | 2 s coarse step, config-validated ≤ ½ the minimum window (PR-R03) | Short edge-of-field windows. |
| A1-11 | §7.4, FR-SIM-002 | `solver_timeout_seconds` | `max_deterministic_time` + 1 worker in reproducible mode (PR-O07/O08) | A wall-clock limit breaks same-seed replay. |
| A1-12 | §8.2 simulation | Unspecified seeding | One run seed; every stream derived via `aether.rng` (no sub-seeds in config) | Otherwise holdout seeds would share one weather history. |
| A1-13 | §8.2, §13.9 | One scenario file | `configs/base.yaml` (benchmark, no scripted events) and `configs/demo.yaml` (extends base, adds PR-W20) | Keeps the demo's scripted cloud event out of the benchmark. |
| A1-14 | §7.5 B1 | "Arrival order" | Seeded Poisson request stream (PR-E07) served in arrival order | B1 needs requests to exist. |
| A1-15 | §9.2 metrics | Fixed-mass threshold implied | High-impact defined as a mean rate (PR-E02). Undefined recall excluded and counted. Per-regime and observed-at-least-once breakdowns | Scales across horizons; avoids undefined metrics. |
| A1-16 | §9.4 statistics | One success comparison | Holm correction across m1–m4; `adaptive_eig` vs `greedy_eig` reported with equal prominence; holdout seed count from a power rule | Multiplicity, and a fair comparator. |
| A1-17 | §11.1 entities | — | Added `AcquisitionOption`, real `Acquisition` (P0), `UncertaintyKind`, `MissingReason`, `AcquisitionStatus`; `SimulatedAcquisition` drops true wind and cloud fields | Closed vocabularies; no inferred non-detections; no truth leakage. |
| A1-18 | §11.4 example config | Inline numbers | Superseded by `configs/base.yaml` and `Parameter_Register.md` | One source of truth. |
| A1-19 | §15, §12, §13 | Brief | `Parameter_2.md` Parts D (security), E (API), F (UX), G (ops/QA), H (governance) adopted as written | They fill real gaps and don't conflict with the register. |
| A1-20 | §18.1 repo layout | `inference/`, `optimization/`, `docs/`, `configs/*_profiles/` | Actual layout: `belief/`, `planning/`, `contracts/`, `Implementation/` for specs, `configs/sensors/`, `configs/spacecraft/`, `configs/scenarios/` | Match the tree. |
| A1-21 | §18.2–18.3 workstreams | 6 workstreams, no lanes | 9 lanes for 3 Claude + 6 Codex agents with exclusive directory ownership (`Work_Plan.md`) | Parallel agents need conflict-free ownership. |
| A1-22 | §25 citations | S01–S15 | Add S16 Cusworth 2021, S17 Tanager specs, S18 Tanager detection-limit studies, S19 Jacob 2016; DOI for S08 (Register, "Added citations") | Configs rely on them. |
