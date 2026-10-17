# AETHER — Lessons Learned, Mistakes, and Fixes

**Prepared:** 17 October 2026 · **Status:** Review of work in progress. Nothing here is a measured result.
**Reviewed:** `AETHER_Product_Requirements_Document.md` (PRD v1.0), `Parameter_1.md` (concept [C00]),
`Parameter_2.md` (gap review), `configs/**`, `experiments/**`, `backend/aether/**` (contracts, config,
rng, cli, package interface docstrings), `backend/tests/unit/*`, `scripts/feasibility/pass_budget.py`.

> The repo was changing while this was written. Re-check each item against the current tree before acting
> on it. Items are tagged **[BUG]** (wrong as written), **[RISK]** (will go wrong if nothing changes),
> **[DRIFT]** (docs and code disagree), **[GOOD]** (keep doing this).

---

## 0. Summary: the ten lessons that matter most

1. **There are three competing parameter sources, and a fourth that doesn't exist.** PRD §11.4,
   `Parameter_2.md` (ENG-* IDs) and `configs/*.yaml` (PR-* IDs) give different numbers for the same
   quantities. The configs cite `Implementation/Parameter_Register.md`, which isn't in the repo. (§1.1)
2. **Review findings were written down and then not applied.** `Parameter_2.md` G-01 says to stop using
   a wall-clock CP-SAT limit. `demo.yaml` still uses `time_limit_seconds`. G-02 says in-process truth
   isolation is unenforced. `ScenarioBundle` still carries `truth` and `model` in one object. (§1.2)
3. **The benchmark may not be able to tell the policies apart.** 85% of sources forget their state in
   2–8 h, but daylight passes come in clusters about 21 h apart. Most observations will have decayed
   to the prior before the next pass. This needs a power check before any holdout run. (§2.1)
4. **The "well-specified" control (m0) isn't well specified.** Truth has hourly flux variability
   (σ_ln 0.30) that the belief model treats as static flux. (§2.2)
5. **The false-positive detection likelihood multiplies a probability by a density for z=1 but not
   for z=0.** That makes the posterior depend on flux units. (§2.3)
6. **True wind and cloud values flow into the belief update** through `SimulatedAcquisition`. That is
   a small truth leak, and it weakens the misspecification families. (§2.4)
7. **The demo's scripted cloud event is in the benchmark base config,** so every holdout run would
   include it. (§2.6)
8. **Sub-seeds are hardcoded** (`weather.seed: 42018`, `solver.random_seed: 42019`). If only
   `random_seed` changes per run, all 100 holdout seeds share one weather history. (§2.7)
9. **The "independent" feasibility checker shares `slew_time_s` with the solver** and uses mid-window
   line of sight. A bug there passes both. (§2.9)
10. **P0 scope grew without the PRD being updated:** 4 satellites instead of 1–2, 5 policies instead of
    2, and new enums and regimes. Some of these are good decisions. They need to be written into the
    PRD so the PRD stays authoritative. (§1.3)

---

## 1. Process and documentation lessons

### 1.1 [DRIFT] One quantity, three values: parameters have no single source of truth

| Quantity | PRD §11.4 / text | `Parameter_2.md` | `configs/` (what code will use) |
|---|---|---|---|
| Source-state model | single 2-state Markov, P(1→1)=0.97, P(0→1)=0.03 | same (ENG-BEL-002/003) | **3-regime mixture** (persistent/intermittent/episodic) |
| Rate prior | — | lognormal, median 400, σ 1.0 | lognormal, median 300, σ 1.1 |
| Flux grid | — | 200 bins, 10–20 000 kg/h | 64 bins, 10–50 000 kg/h |
| POD family | "logistic-like in flux" | logistic in **Q**, Q50 = 500 kg/h | logistic in **ln Q**, Q50 = 100 kg/h, scaled by wind and GSD |
| False-positive rate | — | 0.01 | 0.02 |
| GSD / exposure | — | 60 m / 10 s | 30 m / 3 s |
| Max off-nadir | — | 30° | 40° |
| Slew / settle | — | 1.0 °/s / 10 s | 1.5 °/s / 5 s |
| Data per scene | — | 2 GB | 306 MB |
| Max acquisitions per orbit | — | 4 | 10 |
| Validity | — | `1 − cloud`, hard invalid above 0.3 | `0.95 × (1 − cloud) × geometry penalty`, no hard threshold |
| Cloud correlation length | — | 50 km | 150 km |
| Freeze rule | "declared freeze window" | 30 min | `freeze_current_pass: true` |
| Solver limit | `solver_timeout_seconds: 20` | `max_deterministic_time` 30 | `time_limit_seconds: 10` (wall clock) |
| P0 sources / spacecraft | 10–20 / 1–2 | 15 / 2 | 20 / 4 |
| Dev / holdout seeds | — | 20 / 30 | 30 / 100 |
| Parameter IDs | — | `ENG-*`, `SEC-*`, `UX-*` | `PR-*` → `Parameter_Register.md` (**missing**) |

**Why it's a problem.** Each engineer reads a different document, and benchmark numbers stop being
comparable. Reviewers can't trace a config value to its rationale, which undermines the [A]/[D]
tagging discipline the PRD depends on.

**Fix.**
- Create **one** machine-readable registry, `configs/parameters.yaml` (the shape is already proposed
  in `Parameter_2.md` Part B), with one ID scheme. Every YAML comment cites an ID that exists in it.
- Add a CI test that checks every `PR-*`/`ENG-*` ID in `configs/` and `backend/` against the registry.
  It fails on dangling IDs.
- In the PRD and `Parameter_2.md`, replace the numeric tables with "see registry ID X". Keep the
  rationale and drop the numbers, so they can't drift again.
- Record *why* the configs departed from `Parameter_2.md` (for example, 30 m / ln-Q POD: "Tanager-class
  anchors"). Those choices may be better, but right now the reasoning is lost.

### 1.2 [RISK] Review findings were written down and not tracked to closure

`Parameter_2.md` Part A is a good review. Its fixes didn't reach the code:

| Finding | Status in code |
|---|---|
| G-01 CP-SAT non-determinism: use `num_workers=1` **and** `max_deterministic_time` | `num_workers: 1` applied. Limit is still the wall-clock `time_limit_seconds: 10`. With a wall-clock limit, the incumbent at cutoff depends on machine load, so same-seed replay (T-EVAL-02) can fail. |
| G-02 truth isolation is unenforced in-process | `ScenarioBundle(model, truth)` hands both views to anything that receives the bundle. An AST name-lint (`test_truth_isolation.py`) is a useful tripwire, but it isn't a boundary. `getattr(bundle, "tr" + "uth")` passes it. |
| G-03 IERS/ephemeris downloads break offline runs | `pass_budget.py` calls `load('de421.bsp')`, which downloads at runtime, and `.gitignore` excludes `*.bsp`. |
| G-04 canonical hashing (RFC 8785) | `json.dumps(sort_keys=True)` is close but not JCS. It's fine if documented as the canonical form. Pick one and write it down. |
| G-06 B1 "arrival order" needs a request generator | No request generator in config (ENG-SIM-006 not carried over). |

**Lesson.** A review document isn't a work queue. Findings get lost when they live only in prose.

**Fix.** Open one issue per finding ID (G-01…G-10), each with an acceptance test, and close it only when
the test exists. Add a "Findings status" table to the top of `Parameter_2.md`.

### 1.3 [DRIFT] P0 scope and contracts grew without the PRD

- `demo.yaml` has **4** virtual spacecraft (PRD P0: 1–2), **5** policies (P0: 2), and 20 sources (top of
  the 10–20 range).
- `enums.py` adds `SHORT_WINDOW`, `HEURISTIC`, `GREEDY_EIG`, `BELIEF_PREDICTED`, `FORECAST_REVISED`, and a
  `Regime` enum. None of these are in the PRD. The file's own rule says "adding a member is a contract
  change: open a PR". These were added in the first drop.
- `configs/scenarios/README.md` calls the misspecification families **P0**. PRD FR-SIM-008 lists them as
  **P1**.
- New concepts with no PRD definition: "lanes L1–L9", task IDs (`SCI-03`, `ORB-01`, `PR-F01`, …), and
  `Implementation/Work_Plan.md` (referenced from `cli.py` and `ingestion/__init__.py`, not in the repo).

**Lesson.** Several of these are *improvements*. Making misspecification families P0 is the right call,
because without them the adaptive "win" is circular. But if the PRD isn't updated, it stops being the
spec, and reviewers judge the code against a document it no longer follows.

**Fix.** Either cut back to PRD P0 (2 sats, 2 policies) or amend PRD §3.1, §7.5, §9.1 and FR-SIM-008.
Recommendation: amend, keep 4 sats only if the pass budget (§2.1) needs them, and add `Work_Plan.md` or
remove the references to it.

### 1.4 [DRIFT] Repo layout differs from PRD §18.1

The PRD specifies `docs/`, `configs/sensor_profiles/`, `configs/spacecraft_profiles/`,
`backend/aether/inference/`, `optimization/`, `geometry/`, and `provenance/`. The repo has
`Implementation/`, `configs/sensors/`, `configs/spacecraft/`, `belief/`, `planning/`, and `contracts/`.
Either is fine. Update §18.1 to match what exists.

### 1.5 [RISK] Hygiene

- Everything except the PRD and `Parameter_1.md` is **untracked** (`backend/`, `configs/`,
  `experiments/`, `scripts/`, `Parameter_2.md`). One bad `git clean` loses it, and the pre-registration
  argument ("lock the protocol before holdout") needs commit history. Commit early.
- `Parameter_1.md` is the concept document [C00], not a parameter set. Rename it to `concept.md` and
  strip the chat paste residue ("NASA Open Data Portal +1", "AAAI +1", "dw.com").
- `README.md` says AETHER will "verify" emissions, which contradicts PRD principle 7. Use "collect
  evidence on" or "corroborate".
- Configs cite literature that isn't on the Citations Board: Cusworth et al. 2021 (`permian.yaml`) and
  Jacob et al. 2016 (POD wind scaling, sensor YAML). Add them as S16/S17 or remove the claims.

---

## 2. Scientific and modeling lessons

### 2.1 [RISK] The benchmark may be unable to discriminate between policies

**Memory vs revisit.** From the configured regimes (`correlation_time = −1/ln(1 − 1/on − 1/off)`):

| Regime | Weight | Stationary P(active) | State correlation time |
|---|---|---|---|
| Persistent (240 h on / 48 h off) | 0.15 | 0.83 | ≈ 40 h |
| Intermittent (12 / 24) | 0.45 | 0.33 | ≈ 7.5 h |
| Episodic (3 / 72) | 0.40 | 0.04 | ≈ 2.3 h |

**Revisit.** My rough two-body estimate (circular 500 km orbits, epoch Sun position, 16-point Permian
grid, off-nadir ≤ 40°, Sun elevation ≥ 20°, 2 s step) for the 4-sat config over 72 h gives about
**8 daylight regional passes**. They come in morning/afternoon clusters near **T+17–21 h, T+41–44 h and
T+65–69 h**, and nothing happens in the first ~17 h. This is an estimate, not SGP4. `pass_budget.py` is
the authoritative check and should be run.

**Consequence.** An observation of an intermittent source is about `e^(−21/7.5) ≈ 6%` remembered by the
next pass cluster. An episodic source's observation is gone within hours. Brier is scored every 6 h over
all 20 sources, so most of the score comes from sources whose belief has relaxed back to the prior under
*every* policy. The `test_regime_math` comment ("correlation time must exceed typical revisit spacing
(~10 h)") checks only the persistent regime (15% of sources), and the real spacing is closer to 21 h than
10 h.

**Capacity.** Each pass is about 120 s long. Each acquisition costs 3 s of exposure, plus a slew at
1.5 °/s, plus 5 s of settling. That gives roughly 5–8 acquisitions per pass, or ~40–60 over 72 h for 20
sources. Energy (0.2 Wh/scene vs ~75 Wh usable) and storage (64 GB ≈ 209 scenes) never bind in m0. If
capacity is close to demand, every policy observes nearly everything, and the policies differ only in
order.

**Fix: add a "discriminability gate" before any holdout run.**
- Run two reference policies on dev seeds: **random-feasible** (lower bound) and **oracle** (sees truth;
  upper bound). If the oracle-minus-random Brier gap is inside the seed-to-seed noise, no policy can show
  significance. Change the scenario, not the planner.
- Report Brier per regime and on "observed-at-least-once" sources, alongside the all-source score.
- Choose source count and visit caps so demand clearly exceeds capacity (for example, ≥ 2× sources per
  available acquisition slot). State the ratio in the protocol.
- Estimate the number of seeds needed from the dev-seed variance of the paired difference. Don't assume
  100.

### 2.2 [BUG] m0 "well-specified" is misspecified

Truth (`simulation/__init__.py`) uses `q[t] = Q_i · exp(ε_t)` with `hourly_variability_sigma_ln: 0.30`.
The belief (`belief/__init__.py`) holds flux static and "folds hourly variability into the measurement
noise", but the measurement noise in the sensor config is `σ_ln = 0.35`, not `√(0.35² + 0.30²) ≈ 0.46`.
The flux posterior will be overconfident even in the control family, so the `flux_interval_coverage_90`
metric will fail for reasons unrelated to the planner.

**Fix.** Compute the belief's effective noise from the config, `σ_eff = √(σ_meas² + σ_hourly²)`, and add a
test that m0 truth and model imply the same observation distribution. More generally, add an
"m0 calibration test": on m0 dev seeds, 90% intervals must cover about 90% and the reliability diagram
must be flat within sampling error. If the control fails calibration, nothing downstream means anything.

### 2.3 [BUG] Detection likelihood mixes a probability with a density

`belief/__init__.py`: `DETECTION: lik = P(det|z,q) · N(ln meas; ln q, σ) (flux term only if z=1)`.
For z=1 the likelihood is probability × density (per unit ln flux). For z=0 (false positive) it is a bare
probability. The ratio between them then depends on the measurement units, so the same data gives
different posteriors in kg/h and kg/s.

**Fix.** Give false positives an explicit flux density `f_FP(ln meas)` (for example, the prior predictive
or a broad lognormal near the detection limit) and use `P(det|z=0) · f_FP(ln meas)`. Add a unit-invariance
test: rescaling all fluxes by a constant must leave `p_active` unchanged.

Also fix the `sensors/__init__.py` docstring, which gives two definitions of active-source detection
(`pod(q)` and `1 − (1−pod)(1−fp)`). Pick one, and make the simulator and the belief use the same one in m0.

### 2.4 [RISK] True environment flows into the belief

`SimulatedAcquisition` carries `wind_m_s` and `cloud_fraction`, and `SourceBelief.update(..., wind_m_s=...)`
takes wind. If the runner passes the acquisition's wind, the planner side learns the *true* wind. That is
a leak of `SIMULATED_GROUND_TRUTH` into `MODEL_INFERENCE`. It also makes m3-style weather
misspecification weaker than intended.

**Fix.** Split the fields: `wind_true_m_s` stays in truth, and `wind_estimate_m_s` (truth plus a
configured reanalysis-style error) goes on the acquisition. Add a canary test: perturb the true wind, and
the belief update must not change.

### 2.5 [RISK] The objective is misaligned with the metric

- The planner maximizes **one-step binary EIG at acquisition time**. The primary metric is **Brier
  averaged over 6-hourly evaluation times**. An episodic source can have high EIG and almost no Brier
  value, because its state decorrelates in about 2 h.
- The belief has a regime dimension, but EIG ignores regime information, which is the only information
  that lasts. The adaptive planner is therefore myopic in exactly the way that matters for the metric.
- The primary metric (activity Brier) is close to what `adaptive_eig` optimizes, while `largest_first`
  optimizes something else. The success criterion compares only against `largest_first`, not
  `greedy_eig` (the strong comparator PRD §7.5 asks for). A win under this design is partly built in.

**Fix.**
- Define utility as the **expected reduction in summed Brier over the evaluation times until the next
  plausible revisit**, or at least discount EIG by `exp(−Δt/τ_regime)` under the current regime mix. This
  is still closed form on the 3×2×G grid.
- Add `adaptive_eig` vs `greedy_eig` to the success criterion (or as a mandatory secondary), and give
  high-impact recall and corroboration latency the same reporting weight as Brier (PRD RQ2).
- The "≥ 2 of 4 families" clause adds multiplicity. Use Holm–Bonferroni across families or state the
  family-wise error explicitly.

### 2.6 [BUG] The demo script contaminates the benchmark

`protocol.yaml` uses `base_config: configs/demo.yaml`, and `demo.yaml` contains
`injected_events: forecast_revision at hour 20 on source 0` (the golden-demo step 5). Every benchmark run
would have a hand-placed cloud event that also overwrites the forecast (perfect information). This
changes results, and it can be read as a scripted advantage.

**Fix.** Split the config into `configs/base.yaml` (benchmark, no injected events) and `configs/demo.yaml`
(base plus demo events). Add a test that the protocol's base config has `injected_events == ()`.

### 2.7 [RISK] Seed derivation makes every holdout run share weather

`random_seed: 42017`, `weather.seed: 42018`, and `planner.solver.random_seed: 42019` are all fixed in the
base config. `cli simulate --seed 1000` presumably overrides only `random_seed`. If weather uses
`weather.seed`, all 100 holdout seeds share one cloud and wind history, so seed-to-seed variance is
underestimated and the CIs are too narrow.

**Fix.** Remove the sub-seeds from config. Derive every stream from the run seed through the existing
`keyed_rng(seed, namespace, …)` (namespaces `"weather"`, `"truth"`, and so on). Add a test that two run
seeds produce different weather and two policies with the same seed produce identical weather.

The `"outcome"` key `(source, sensor, minute)` omits the spacecraft. All 4 sats share `vs_a_point_source`,
so two sats imaging one source in the same minute would get identical draws. That is unlikely with the
current phasing, but cheap to fix by adding `spacecraft_id`.

### 2.8 [BUG] Small numeric and wording errors

| Where | Says | Actually |
|---|---|---|
| `configs/scenarios/README.md`, m1 | "2× more episodic sources" | 0.40 → 0.60 is **1.5×** (persistent halves correctly) |
| `configs/scenarios/README.md`, r1 | "1.5 GB (~5 scenes/orbit)" | 1.5e9 / 3.06e8 = 4.9, so **4** scenes fit |
| `vsat_*.yaml` `raan_deg` comment | "(LTAN−12h)·15" next to an `ltdn` key | The values (359°, 44°) are correct for LTAN = LTDN + 12 h. Spell out the conversion. |
| `test_config.py` comment | "typical revisit spacing (~10 h)" | Pass clusters are ~21 h apart (§2.1) |
| `evaluation.high_impact_threshold_t_ch4: 20` | fixed tonnes over horizon | Doesn't scale to `h168` (7/3× more mass). Back-of-envelope gives ~3 high-impact sources per 20, and ~5% of seeds have **zero**, so `recall@5` is undefined there. Define the threshold as a rate (t/day) and specify how undefined recall is handled. |
| `RegimeConfig.correlation_time_hours` | `mean_on_hours > 1` | `1/on + 1/off ≥ 1` (for example on = off = 1.5 h) gives `ln(≤0)` → crash. Validate `p_on_to_off + p_off_to_on < 1`. |

### 2.9 [RISK] The feasibility checker isn't fully independent

- `orbit/__init__.py`: "One shared implementation: the solver AND the independent checker both call
  `slew_time_s`". A wrong slew model then passes both. That is the failure FR-ORB-007 exists to catch.
- `slew_time_s` uses `los_unit_ecef_at_mid`, but the solver picks the start time *anywhere inside* the
  window. For a 120 s window the LOS swings by tens of degrees between window edges, so the mid-window
  angle can be badly off.
- The CP-SAT slew rule is described as "pairwise implications for every pair whose gap cannot fit". With
  variable starts, a pair can be compatible only for some start times. That needs a conditional
  precedence constraint (`start_j ≥ end_i + slew_ij` if both are chosen and i is before j), not a static
  exclusion.

**Fix.** The checker recomputes LOS at the *chosen* start and end times from its own propagation call and
its own angle math. The solver may use a conservative bound (the maximum slew over both windows), so any
plan it emits is feasible. Add a mutation test: break `slew_time_s` on purpose and confirm the checker
catches it.

### 2.10 [RISK] The pass-search step is coarser than the minimum window

The orbit interface specifies 10 s coarse sampling. The minimum usable window is exposure + settle =
3 + 5 = 8 s, and `Parameter_2.md` ENG-ORB-001 says the step must be < ½ × the minimum window. Edge-of-
field windows of 8–20 s will be missed some of the time. The rough estimate in §2.1 already shows windows
as short as 16 s at a 2 s step.

**Fix.** Use a step ≤ 4 s (or ≤ min window / 2, computed from config) before refinement, and test against a
hand-placed target known to have a short edge window.

### 2.11 [RISK] Contracts are less immutable than they claim

- `frozen=True` is shallow. `raw_properties`, `geometry_geojson`, `payload`, `objective_weights` and
  `regime_probs` are mutable `dict`s inside "immutable" records, which also undermines `payload_sha256`.
- `model_copy(update={"provenance_class": ...})` and `model_construct()` skip validators, so
  "PlumeObservation must be REAL_OBSERVATION" can be bypassed in one line. Typing the field as
  `Literal[ProvenanceClass.REAL_OBSERVATION]` doesn't stop `model_construct` either, but it makes the
  intent checkable by mypy.
- `BeliefSnapshot` has no provenance validator (other models do), no check that `regime_probs` sums to 1,
  and no check on `ci90` ordering.
- `CandidateUtility.integer_utility` isn't checked against `round(utility × scale)`, and
  `ObservationWindow.los_unit_ecef_at_mid` isn't checked to be a unit vector.
- **No real `Acquisition` contract.** PRD FR-DATA-006 and §11.1 need acquisitions that exist without a
  plume. Without one, the first person who needs "EMIT looked here" will be tempted to infer it from plume
  rows, which is the exact non-detection mistake the PRD forbids.
- `uncertainty_kind` and `missing_rate_reason` are free `str`, while every other vocabulary is a closed
  enum.

**Fix.** Use `tuple`/`frozendict`-style or `MappingProxyType` fields (or store the canonical JSON string
plus its hash). Add `Literal` provenance types, `UncertaintyKind`/`MissingReason` enums, and a real-data
`Acquisition` model. Add a test that `model_copy(update=...)` with a foreign provenance class is caught at
the next validation boundary (re-validate on every lane hand-off).

---

## 3. What went right (keep doing this)

- **[GOOD]** Provenance classes are enforced in constructors and tested (`test_simulated_cannot_claim_real_provenance`).
- **[GOOD]** Override paths fail loudly on unknown keys. A typo in a misspecification family can't
  silently become a no-op.
- **[GOOD]** `truth:` overrides with a test that the model view is untouched. This is the right mechanism
  for non-circular evaluation.
- **[GOOD]** Keyed RNG with a closed namespace registry that rejects unknown namespaces.
- **[GOOD]** The AST leakage test exists from day one. Strengthen it (§1.2), don't remove it.
- **[GOOD]** An independent pass-budget script, written before the orbit lane, to cross-check it.
- **[GOOD]** Pre-registered protocol, disjoint dev/holdout seed lists, and "report all families either
  way".
- **[GOOD]** Every config number is tagged [A]/[D]/[E]. The tags just need an existing registry to point to.

---

## 4. Required PRD changes and expansions

| PRD section | Change |
|---|---|
| §3.1 P0 scope | Reconcile with configs (spacecraft count, policies, sources). Promote misspecification families (FR-SIM-008) to **P0**. |
| §3.4 stage gates | Add **G4.5 Discriminability**: oracle vs random gap exceeds dev-seed noise, and the capacity/demand ratio is reported, before any holdout run. Add an **m0 calibration** pass condition to G3. |
| §5.4 source state | Replace the single 2-state chain with the 3-regime mixture HMM actually being built (static regime, per-regime Markov chain, static flux plus hourly variability). State how hourly variability enters the likelihood. |
| §5.5 / §5.6 likelihood | Specify the false-positive flux density. Define **observed vs true** environment (wind/cloud estimates with error models). One definition of P(det \| active). |
| §7.1–7.2 objective | State the EIG target's relation to the evaluation metric. Add time-discounted or Brier-reduction utility as the P0 default or as an ablation. Document that regime information is ignored by one-step binary EIG. |
| §7.3 constraints | Specify slew as conditional precedence over variable start times, and how the checker recomputes it independently. |
| §7.5 / §9.4 | Success criterion includes `greedy_eig`. Add random-feasible and oracle reference policies (not competitors). Add a multiplicity rule. |
| §8.2 simulation | Seed derivation (one run seed → all streams). Demo/benchmark config split. Pass-based replanning cadence and freeze rule. Request generator for B1. |
| §9.2 metrics | High-impact threshold as a rate. Rule for undefined recall. Per-regime and observed-only Brier breakdowns. |
| §10.1 trust boundaries | P0 isolation mechanism for the in-process CLI (separate process, or an `observe()`-only interface; see `Parameter_2.md` SEC-ISO). |
| §11.1 entities | Add the real-data `Acquisition` contract to P0 tasks. Closed enums for uncertainty kind and missing reason. |
| §11.4 example config | Delete the inline numbers and point to `configs/base.yaml` plus the parameter registry. |
| §18.1 repo layout | Match the actual tree. Add `parameters.yaml`, `Work_Plan.md`, `lessons.md`. |
| §20 open decisions | Move resolved items (region = Permian, regime model, sensor anchors) to an ADR/decision log with dates. |
| §25 Citations | Add Cusworth et al. 2021 and Jacob et al. 2016, or drop the config claims that rely on them. |
| New § "Parameter governance" | One registry, one ID scheme, CI check for dangling IDs, rule that docs cite IDs, not numbers. |
| New § "Review closure" | Every review finding becomes a tracked issue with an acceptance test, and its status table lives at the top of the review doc. |

---

## 5. Action list, in order

**Before more code is written**
1. Commit the untracked work. Rename `Parameter_1.md` → `concept.md`.
2. Create `configs/parameters.yaml` with one ID scheme. Make every config comment resolve to it, and add
   the CI dangling-ID check.
3. Split `base.yaml` from `demo.yaml`. Point the protocol at `base.yaml`.
4. Replace `time_limit_seconds` with a deterministic-time limit for reproducible mode.
5. Remove hardcoded sub-seeds and derive them from the run seed. Add the different-seeds/different-weather
   test.

**Before the belief and simulator are finished**
6. Fix the false-positive likelihood density. Add the unit-invariance test.
7. Fix m0 consistency (σ_eff) and add the m0 calibration test.
8. Split true and estimated wind/cloud fields. Add the wind-perturbation canary.
9. Add the real-data `Acquisition` contract and closed enums for uncertainty and missing reason.

**Before the planner and checker are finished**
10. Give the checker its own slew/LOS computation at the chosen times, with a mutation test.
11. Use a pass-search step ≤ min window / 2.

**Before any holdout run**
12. Run `pass_budget.py`. Then run oracle vs random on dev seeds. Report capacity/demand and the
    discriminability margin, and resize the scenario if the margin is too small.
13. Update the PRD sections in §4, then set `locked: true` in `protocol.yaml` and tag the commit.
