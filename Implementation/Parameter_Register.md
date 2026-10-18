# AETHER — Parameter Register (P0)

**Status:** v1.1, 17 Oct 2026. This is the single source of truth for every number in `configs/`. A CI test (`backend/tests/unit/test_parameter_registry.py`) fails if a config or code comment cites a PR-ID that has no row here.
**Tags:** **[E]** sourced fact · **[A]** assumption (anchored to a source where one exists; must be sensitivity-tested) · **[D]** design decision · **[V]** to be verified by a named task before it is relied on.
**Rule:** a number used in code that is not in this register is a bug. To change a value, update this file and the config in the same PR, and give the reason.

---

## 0. Review of `Parameter_1.md` (the concept text)

`Parameter_1.md` is the original ChatGPT concept (the PRD cites it as [C00]). It contains **no numerical parameters**: only the qualitative design, which the PRD already formalizes. Findings:

| # | Finding | Action |
|---|---|---|
| 1 | No values for orbits, sensor, POD, persistence, flux priors, weather, budgets or metrics thresholds. | Supplied in this register (§2–§9). |
| 2 | Citation chips were lost in the copy-paste ("NASA Open Data Portal +1", "AAAI +1", "AMT", a stray "dw.com"). The claims they supported have no links. | Re-sourced below where it mattered. |
| 3 | "A 2026 analysis of observation geometry" (AMT) is cited for IME but is not identifiable. | Use Varon et al. 2018 [S07] for IME instead. Treat the 2026 citation as unverified. |
| 4 | "A 2024 paper on non-detections across sensors" = Ayasse et al. 2024, ES&T, DOI `10.1021/acs.est.4c06702` [S08]. Reports EMIT 90% POD ≈ 1000 kg/h at 3 m/s. | Used as an anchor for the P1 wide-swath sensor. |
| 5 | The concept (and the PRD) suggest **1–2 satellites over 72 h**. Measured with real orbit math (§1), that gives only **2–3 regional passes**, too few decision points for adaptive replanning to matter. | **Changed to 4 virtual satellites, ±40° off-nadir** (6 passes / 72 h). |
| 6 | The PRD's example persistence (0.97/h stay-on, 0.03/h restart) settles at P(active) = 0.5 with a ~17 h memory. Beliefs forget everything between passes, so information gain becomes meaningless. | Replaced with a 3-regime model calibrated to Permian intermittency data (§4). |
| 7 | "Carbon Mapper public data is for non-commercial public-good uses" is plausible but unverified. | **[V]** ING-06 must record the actual Terms of Use before any Carbon Mapper record is stored. |

## 0a. Relationship to `Parameter_2.md` (ENG-*, SEC-*, API-*, UX-* IDs)

`Parameter_2.md` is a gap review that also proposes values. To keep one source of truth:

- **Engineering values (its Part C, ENG-ORB/SC/SEN/WX/BEL/OPT/SIM):** superseded by this register. Where the numbers differ, this register wins for the reasons below. Its *rules* are adopted: deterministic solver time, step < ½ min window, Poisson request generator for B1, canonical hashing, keyed RNG, replay tolerance.
- **Security, API, UX, Ops, QA, Governance (its Parts D–H):** adopted as written. They don't conflict with anything here. They are owned by L1 (SEC, OPS, GOV), L9 (API, UX) and L8 (QA) in `Work_Plan.md`.

| Quantity | Parameter_2 | This register | Why this register differs |
|---|---|---|---|
| Source-state model | single chain, 0.97 / 0.03 per h | 3-regime mixture (PR-P20–22) | Single chain settles at P = 0.5 with ~17 h memory and isn't anchored to data. The regime mix matches Permian intermittency [S16]. |
| Sensor class | 60 m, 10 s, Q50 = 500 kg/h, logistic in Q | 30 m, 3 s, Q50 = 100 kg/h, logistic in ln Q, wind and GSD scaling (PR-V*) | Anchored to published Tanager-class performance [S17, S18] and the Jacob 2016 scaling [S19]. A logistic in ln Q stays monotone and well-shaped across 3 orders of magnitude. |
| Validity | 1 − cloud with hard invalid above 0.3 | 0.95 × (1 − cloud) × geometry penalty, no hard cutoff (PR-V30–32) | A hard threshold makes EIG discontinuous and invites gaming at 0.3. |
| Off-nadir / slew / settle | 30° / 1.0 °/s / 10 s | 40° / 1.5 °/s / 5 s (PR-A01–03) | At 30° the 4-sat constellation gets 5 passes and 3 windows per target (§1). 40° is needed for revisits. |
| Data per scene / acquisitions per orbit | 2 GB / 4 | 306 MB / 10 (PR-V50, PR-A21) | 2 GB is ~7× a 600 × 600 × 425-band cube. The r1 family exercises scarce storage on purpose. |
| Satellites / sources | 2 / 15 | 4 / 20 (PR-P01, §1) | 2 satellites give 3 regional passes in 72 h, too few decisions. |
| Cloud correlation length | 50 km | 150 km (PR-W02) | Synoptic-scale fields. Sweep 50–300 km in the sensitivity study. |
| Flux grid | 200 bins, 10–20 000 | 64 bins, 10–50 000 (PR-B01) | The prior tail reaches 30 000 kg/h. 64 bins is about 0.17 ln units per bin, finer than the 0.46 effective measurement σ. |
| Seeds | 20 dev / 30 holdout | 30 dev / ≤ 100 holdout, count set by a power rule (`protocol.yaml`) | Holdout size follows from dev-seed variance, not a fixed guess. |

## 0b. Closure of `lessons.md` findings

| Finding | Status | Where |
|---|---|---|
| 1.1 Three parameter sources | **Fixed.** One register; Parameter_2 values reconciled (§0a); dangling-ID CI test. | this file, `test_parameter_registry.py` |
| 1.2 G-01 wall-clock solver limit | **Fixed.** `mode: reproducible`, `max_deterministic_time`, `num_workers=1`, config-validated. | PR-O07/O08 |
| 1.2 G-02 in-process truth isolation | **Partly fixed.** AST guard plus contracts that carry no truth; runner gives policies `bundle.model` and a forecast-only weather view (SIM-06). A separate scorer process is P1 (Parameter_2 SEC-ISO-001). | `simulation/__init__.py` |
| 1.2 G-03 runtime ephemeris download | **Task.** ORB-07 pins DE421 with SHA-256 under `data/ephemeris/`. | Work_Plan |
| 1.2 G-04 canonical hash | **Fixed (documented).** Canonical form written in `ScenarioConfig.config_hash`. | `config.py` |
| 1.2 G-06 B1 request generator | **Fixed.** PR-E07 Poisson stream, rng namespace `requests`. | PR-E07 |
| 1.3 Scope drift from PRD | **Fixed.** `Implementation/PRD_Amendments.md` records every change. | — |
| 2.1 Discriminability | **Gate added.** G4.5 oracle-vs-random gate, per-regime and observed-only breakdowns, capacity/demand reported. | `protocol.yaml`, EVL-08 |
| 2.2 m0 not well specified | **Fixed in spec.** σ_eff = √(0.35² + 0.30²) = 0.46 in the belief; m0 calibration test (SCI-10). | `belief/__init__.py` |
| 2.3 Probability × density | **Fixed in spec.** False-alarm flux density PR-V21; one detection definition; unit-invariance test. | `sensors`, `belief` docstrings |
| 2.4 True wind into belief | **Fixed.** `SimulatedAcquisition` has `wind_estimate_m_s` (PR-W13) only; test asserts no true-wind field. | `contracts/models.py` |
| 2.5 Objective vs metric | **Ablation added.** `brier_reduction_to_next_pass` utility (PR-O10, SCI-09); `greedy_eig` comparison mandatory; Holm correction. | `protocol.yaml` |
| 2.6 Demo event in benchmark | **Fixed.** `base.yaml` (benchmark, test-enforced empty events) vs `demo.yaml extends base.yaml`. | configs |
| 2.7 Hardcoded sub-seeds | **Fixed.** Removed; single run seed; `derive_seed`; outcome key includes spacecraft. | `rng.py` |
| 2.8 Numeric/wording errors | **Fixed.** m1 1.5×, r1 4 scenes, RAAN comment, threshold as rate (PR-E02), chain validator. | configs, `config.py` |
| 2.9 Checker not independent | **Fixed in spec.** Discrete AcquisitionOptions with LOS at their own times; checker recomputes with its own propagation; mutation test. | `planning`, `orbit` docstrings |
| 2.10 Coarse step too large | **Fixed.** 2 s; config rejects a step above half the minimum window. | PR-R03 |
| 2.11 Contract immutability | **Partly fixed.** Real `Acquisition` contract; closed enums for uncertainty and missing reason; BeliefSnapshot and LOS validators; runner re-validates at hand-offs. Deep-frozen dict fields deferred (INT-08). | `contracts/` |

---

## 1. Feasibility check: pass budget (PR-F01)

Computed with `scripts/feasibility/pass_budget.py` (sgp4 2.27 + Skyfield 1.55, DE421). 20 random targets in the Permian box, sun elevation ≥ 20°, Earth-visible, off-nadir ≤ limit, 10 s sampling.

| Constellation | Off-nadir | 72 h regional passes | Windows per target (min/median/max) | 168 h passes |
|---|---|---|---|---|
| 1 sat, SSO 10:30 | 40° | 2 | 1 / 2 / 2 | 4 |
| 2 sats, 1 plane | 40° | 3 | 2 / 3 / 3 | 8 |
| **4 sats, 2 planes (chosen)** | **40°** | **6** | **4 / 5 / 5** | **15** |
| 4 sats, 2 planes | 30° | 5 | 2 / 3 / 4 | — |
| 4 sats, 2 planes | 45° | 7 | 5 / 6 / 6 | — |

**Capacity per pass (estimate, [V] ORB-05):** about 15 of 20 targets are visible per pass. At 3 s exposure + 5 s settle + ~10° slew at 1.5°/s, the satellite can image roughly **6–8 targets in its ~170 s regional dwell**. So each pass is genuinely contested and the scheduler's choice matters. Over 72 h that's ~40–50 acquisitions for 20 sources: enough for 2–3 revisits per source, which is what adaptivity needs.

**Revisit timing (lessons.md 2.1):** passes come in morning/afternoon clusters about 21 h apart (the two planes cross at 10:30 and 13:30 local time), and none occur at night. Only PERSISTENT sources (τ ≈ 40 h) keep state memory across that gap. INTERMITTENT and EPISODIC sources mostly reveal their *regime* rather than their current state. That's a real property of daylight-only SWIR sensing, not a simulator artefact. It's why gate G4.5, the per-regime breakdowns and the PR-O10 ablation exist.

**Gate G1-F:** if ORB-05 measures fewer than 5 regional passes per 72 h or fewer than 4 acquisitions per pass, switch the demo to `h168_long_horizon` before building further. **Measured 18 Oct 2026 on the integrated pinned scenario: FAIL.** 7 passes; per-pass optimum 9, 10, 9, 6, 10, 8, **2** (`experiments/results/g1f-pinned-base/g1f.json`). The switch is pending human review (`docs/validation-report.md` §6); no number here has changed. A diagnostic on `h168_long_horizon` (fill seed 1000) meets both thresholds: 16 passes, minimum 5 per pass (`experiments/results/g1f-h168-diagnostic/`).

---

## 2. Scenario frame

| ID | Parameter | Value | Tag | Rationale / source |
|---|---|---|---|---|
| PR-S01 | Simulation epoch | 2026-10-17T00:00:00Z | [D] | Explicit virtual epoch, separate from any historical replay. |
| PR-S02 | Horizon | 72 h (demo); 168 h (benchmark sensitivity) | [D] | 72 h from [C00]; 168 h gives 15 passes. |
| PR-S03 | Master seed | 42017; benchmark seeds in `experiments/` | [D] | Dev 1000–1029, holdout 2000–2099. |
| PR-R01 | Region | Permian Basin, bbox [-104.5, 30.8, -101.0, 33.5] | [D] | Densest public point-source record; within EMIT's 52°N–52°S band [S02]; arid; intermittency literature exists. |
| PR-R02 | Time step for beliefs/truth | 1 h | [D] | Matches the Markov chain. |
| PR-R03 | Coarse window search step | 2 s | [D] | Must be ≤ ½ the minimum usable window (3 s exposure + 5 s settle = 8 s). The config validator enforces this. Edge-of-field windows can be 8–20 s long. |
| PR-R04 | Boundary refinement tolerance | 0.1 s (bisection) | [D] | |

## 3. Sources

| ID | Parameter | Value | Tag | Rationale / source |
|---|---|---|---|---|
| PR-P01 | Source count | 20 (P0), 60 (P1 / 168 h) | [D] | PRD §3.1. |
| PR-P02 | Placement | Cluster EMIT V002 plume centroids in the bbox (500 m); fill with uniform-random points if fewer than 20 | [D] | Makes the real data shape the experiment. Each `Source.seeded_from_plume_id` records its origin. |
| PR-P03 | Minimum separation | 500 m | [D] | Below the 18 km scene size, so co-imaging is possible but separate source hypotheses stay distinct. |
| PR-P04 | Plume dataset input | `sources.plume_dataset`: repo-relative manifest path + its SHA-256, or `null` (synthetic-only, all uniform fill). Base (18 Oct 2026): `data/manifests/emit_permian.json` @ `216cf916…982c55`, 20 EMIT V002 Permian records | [D] | One pinned input for every policy and family; the hash enters `config_hash` so a protocol lock binds it. Historical plumes give locations only, never truth fluxes or the prior. Interface: `docs/dataset-interface.md`. |
| PR-P10 | Flux prior, conditional on active | lognormal, median 300 kg/h, σ_ln 1.1, truncated [30, 30000] | [A] | Permian aircraft surveys show a heavy-tailed distribution with medians of a few hundred kg/h (Cusworth et al. 2021 [S16]). Puts much of the population near the VS-A detection threshold, which is where scheduling decisions matter. **[V] SCI-08 (18 Oct 2026):** 73 quantified EMIT V002 Permian rates, median 1,701 kg/h vs prior 308; detection- and quantification-selected, so uninformative about the population prior. Kept [A]. The upper tail (σ_ln) and the EMIT rate-uncertainty definition are on the §10 domain-review list. Details: `docs/model-card-source-state.md`. |
| PR-P11 | Hourly flux variability | lognormal, σ_ln 0.30, i.i.d. | [A] | Folded into measurement noise by the belief model (deliberately mild misspecification). |

## 4. Emission-persistence regimes (2-state Markov per regime, 1 h steps)

Hourly transition probabilities are `p(on→off) = 1/mean_on`, `p(off→on) = 1/mean_off`. The stationary active fraction is π = b/(a+b). Memory (correlation time) is τ = −1/ln(1−a−b).

| ID | Regime | Weight | Mean on | Mean off | π | τ | Tag |
|---|---|---|---|---|---|---|---|
| PR-P20 | PERSISTENT | 0.15 | 240 h | 48 h | 0.83 | 39.5 h | [A] may overstate persistence (SCI-08) |
| PR-P21 | INTERMITTENT | 0.45 | 12 h | 24 h | 0.33 | 7.5 h | [A] may overstate persistence (SCI-08) |
| PR-P22 | EPISODIC | 0.40 | 3 h | 72 h | 0.04 | 2.3 h | [A] may overstate persistence (SCI-08) |
| PR-P23 | Population mean active fraction | — | — | — | **0.29** | — | derived |

**Calibration anchor [E] and known mismatch (SCI-08, found by L2):** Cusworth et al. 2021 (ES&T Letters, DOI `10.1021/acs.estlett.1c00173`) report ~26% average detection persistence on revisits across Permian sources, and about 11% of repeatedly observed sources (123 of ~1,100) seen on 50–100% of revisits. That persistence is measured over sources the survey **detected at least once**, which inflates it relative to the unconditional π. The earlier claim here, that "mean π = 0.29 is consistent with ~0.26", compared two different quantities and was **wrong**.

The like-for-like model analogue (exact enumeration, PR-P20–P22, 3–8 revisits at 24–72 h) is:

| Regime mix | Airborne POD = 1 | POD = 0.6 |
|---|---|---|
| base (0.15 / 0.45 / 0.40) | 0.42–0.59 (0.48 at 5 visits) | 0.36 |
| m1 (0.075 / 0.325 / 0.60) | 0.42 | 0.33 |
| no persistent (0 / 0.5 / 0.5) | 0.36 | 0.29 |

So the base scenario is probably **more persistent than the Permian**, perhaps by up to ~2×. That makes adaptive revisits look easier than they would be. Reaching ~0.26 needs both lower persistence and sub-unity POD, so it isn't a simple weight change. Status: PR-P20–P22 stay **[A], flagged "may overstate persistence"**. The m1 family is the designated lower-persistence sensitivity check. Recalibration (SCI-08b) waits until someone reads the paper's methods section (persistence definition, revisit counts, POD treatment). Scripts: `docs/model-card-source-state.md` (L2).

**Why this matters:** adaptive revisits have value only where τ is comparable to the revisit spacing (~10–12 h). PERSISTENT sources (τ ≈ 40 h) are where AETHER should win. EPISODIC ones (τ ≈ 2 h) are close to unpredictable, and no policy should win there. Report results **per regime**.

**Belief model:** regime is a latent static variable per source, so the filter is a 3 × 2 × G tensor (G = 64 flux grid points, 10–50,000 kg/h log-spaced; PR-B01). Observations therefore teach the filter both the current state and the source's regime. EIG is measured on the binary activity state, in bits (PR-B02; PRD §7.1).

| ID | Parameter | Value | Tag | Rationale |
|---|---|---|---|---|
| PR-B03 | Likelihood quadrature | Gauss–Hermite, 16 nodes per nuisance dimension (hourly ε; wind error) | [D] | Marginalizes the hourly flux variability (PR-P11) exactly, the way truth applies it, instead of only widening the measurement σ. Detection density = N(a; 0, σ_eff) × E[POD \| ε ~ N(μ*, s*)], which reduces to the PR-V41 σ_eff form when POD is constant. 16 nodes: the integrand is a smooth logistic; the EIG Monte Carlo test (SCI-06) agrees within 0.005 bit. Known limit: two acquisitions of one source in the same hour are treated as having independent ε. |
| PR-B04 | Wind uncertainty in the belief | ln U_true ~ N(ln U_est, PR-W13 σ = 0.25), flat-prior inversion of the analysis error; POD wind clip applied per node | [A] | The belief sees only the wind estimate. Ignoring its error makes non-detections look too informative and miscalibrates m0. Flat prior ignores the PR-W10 wind climatology (slight under-shrinkage). The same σ is used for planning-time wind forecasts because the config has no separate forecast wind-error parameter. |
| PR-B05 | EIG / Brier utility outcome space | categories {DETECTION, VALID_NON_DETECTION, INVALID}; measured flux value ignored | [D] | Closed form. The flux value carries a little extra information about z (false alarms report near-threshold fluxes), so both utilities are conservative lower bounds. |
| PR-B06 | Flux prior on the grid | truncated lognormal (PR-P10) integrated exactly over each ln-flux bin | [D] | Register PR-P10 says truncated. **Mismatch:** `simulation/truth.py` currently *clips* (≈1.8 % point mass at 30 kg/h). L6 and L2 must use the same form, or m0 is misspecified; raised with L6. |

## 5. Virtual sensor VS-A (point-source imaging spectrometer)

`calibration_status: SIMULATED_PROFILE`. Tanager-class anchors; **not** a Tanager or EMIT specification.

| ID | Parameter | Value | Tag | Source / note |
|---|---|---|---|---|
| PR-V01 | GSD at nadir | 30 m | [A] | Tanager-1 30 m nadir, 30–43 m by look angle (Carbon Mapper spec [S17]). |
| PR-V02 | Off-nadir GSD growth | gsd/cos(θ)^1 | [A] | Simple isotropic approximation. Matches 43 m at about 45°. |
| PR-V03 | Scene size | 18 × 18 km | [A] | Tanager swath 18.6–24.2 km [S17]. |
| PR-V04 | Exposure / acquisition duration | 3 s | [D] | 18 km at ~7 km/s ground speed. |
| PR-V05 | Minimum sun elevation | 20° (solar zenith ≤ 70°) | [A] | SWIR retrievals degrade at high zenith; spec conditions quote 35–45° zenith [S17, S18]. |
| PR-V10 | POD form | logistic in ln Q, `1/(1+exp(−k(lnQ − lnQ50)))` | [D] | Monotone; zero at Q = 0; standard in controlled-release work. |
| PR-V11 | Q50 / Q90 at reference | 100 / 200 kg/h at U = 3 m/s, GSD 30 m | [A] | Tanager spec 90% POD 90–180 kg/h; observed 90% POD ≈ 200 kg/h in standard mode (Carbon Mapper 2026 presentation); predicted MDL 64–126 kg/h (AMT 2025) [S17, S18]. Gives k = ln9/ln2 = 3.17. |
| PR-V12 | Wind scaling | Q50 ∝ U¹, U clipped [1, 10] m/s | [A] | Detection threshold scales with wind × pixel size (Jacob et al. 2016, ACP, DOI `10.5194/acp-16-14371-2016` [S19]). |
| PR-V13 | GSD scaling | Q50 ∝ GSD_eff¹ | [A] | Same source [S19]. |
| PR-V20 | False-positive probability | 0.02 per valid scene of an inactive source | [A] | Controlled releases reported no false positives [S18]. 0.02 is conservative. Sweep 0–0.05 (m4). |
| PR-V21 | False-alarm reported-flux density | lognormal, median 100 kg/h, σ_ln 0.5 | [A] | Gives P(detect, flux \| inactive) the same units as the active case (a density in ln-flux), so posteriors don't depend on flux units. Spurious detections sit near the threshold. The simulator samples from the same density. |
| PR-V22 | Detection definition | P(det \| active, q) = POD(q); P(det \| inactive) = PR-V20 | [D] | One definition for simulator and belief. |
| PR-V30 | Retrieval success | 0.95 | [A] | Non-cloud failures (glint, surface, processing). |
| PR-V31 | p_valid | 0.95 × (1 − cloud) × (1 − 0.25(θ/θmax)²) | [A] | A cloudy scene is INVALID, never a non-detection (PRD §5.5). |
| PR-V32 | Off-nadir quality penalty | 0.25 at θ = θmax | [A] | Longer slant path, larger pixels. |
| PR-V40 | Flux measurement error | lognormal σ_ln 0.35 | [A] | IME-method uncertainties are typically 30–50% (Varon et al. 2018 [S07]). Wind-dependent version is P1. |
| PR-V41 | Effective belief noise | σ_eff = √(PR-V40² + PR-P11²) = 0.46 | derived | The belief holds flux static while truth varies hourly. Using σ_eff keeps m0 well specified. |
| PR-V50 | Data per scene | 306 MB (600 × 600 px × 425 bands × 2 B) | [D] | Order-of-magnitude for a VSWIR cube. |
| PR-V51 | Energy per scene | 0.2 Wh | [A] | ~45 W payload × ~15 s. Not binding in nominal scenarios (stated honestly). |

**P1 sensor VS-B (wide-swath finder), EMIT-class anchor:** 60 m GSD, ~75 km swath [V], Q90 ≈ 1000 kg/h at 3 m/s [S08], Q50 500 kg/h [A].

## 6. Virtual spacecraft VSAT-A..D

| ID | Parameter | Value | Tag | Note |
|---|---|---|---|---|
| PR-K01 | Altitude | 500 km circular | [D] | Typical EO smallsat. Period 94.62 min (computed). |
| PR-K02 | Inclination | 97.40° | [E] | Sun-synchronous at 500 km (J2 condition). |
| PR-K03 | Eccentricity | 0.0001 | [D] | Near-circular; avoids SGP4 singularities. |
| PR-K04 | Planes (LTDN) | Plane 1 10:30 (A, B); plane 2 13:30 (C, D) | [D] | Two local times diversify illumination and weather sampling. |
| PR-K05 | RAAN | 359.0° (plane 1), 44.0° (plane 2) | [D] | RAAN = RA_sun(epoch) + (LTAN − 12 h)·15°, RA_sun = 201.5° at epoch (Skyfield/DE421). **[V] ORB-02** recomputes and asserts the LTDN within ±2 min. |
| PR-K06 | Phasing | A 0°, B 180°; C 90°, D 270° mean anomaly | [D] | Spreads ground tracks. |
| PR-K07 | Drag | B* = 0 | [A] | Negligible error over 72–168 h for a virtual orbit. |
| PR-A01 | Max off-nadir | 40° | [A] | Agile EO smallsats commonly 30–45°. Pass-budget sweep in §1. |
| PR-A02 | Slew rate | 1.5°/s | [A] | Agile smallsat class. r1 family uses 0.75°/s. |
| PR-A03 | Settle time | 5 s | [A] | |
| PR-A10–12 | Battery | 150 Wh, minimum SoC 40%, initial 90%, +40 Wh per sunlit orbit | [A] | Not binding in nominal scenarios. Kept so the checker and the r1 family exercise it. |
| PR-A20 | Storage | 64 GB (≈ 200 scenes) | [A] | Not binding nominally. r1 sets 1.5 GB (≈ 5 scenes per orbit). |
| PR-A21 | Max acquisitions per orbit | 10 | [D] | Duty-cycle surrogate. |
| PR-A30 | Downlink | fixed 90 min latency surrogate, storage released every orbit | [D] | Explicitly **not** physical downlink (PRD §5.2). |

**Honest note on resources:** in the nominal scenario, **slew and exclusivity are the binding constraints**; power and storage are not. Say so in the demo. The r1 family exists to show the resource constraints working.

## 7. Weather (synthetic; labelled synthetic everywhere)

| ID | Parameter | Value | Tag | Note |
|---|---|---|---|---|
| PR-W01 | Mean cloud fraction | 0.30 | [A] | October Permian is mostly clear. **[V] SIM-02:** compute from ERA5 `total_cloud_cover`, Oct 2018–2024, over the bbox. |
| PR-W02 | Spatial correlation length | 150 km | [A] | Synoptic-scale cloud fields. |
| PR-W03 | Temporal correlation | 12 h (AR(1)) | [A] | |
| PR-W04 | Latent logit σ | 1.5 | [A] | Produces both clear and overcast passes. |
| PR-W05/06 | Forecast error | logit σ = 0.30 + 0.05 × lead hours | [A] | Forecast at 24 h lead has σ = 1.5, about as large as the climatological spread. m3 doubles it. |
| PR-W07 | Forecast issue interval | 6 h | [D] | Triggers `forecast_revision` replans. |
| PR-W10–12 | Wind | lognormal median 4.0 m/s, σ_ln 0.45, AR(1) 6 h, clipped [1, 12] | [A] | **[V] SIM-02:** check against ERA5 10 m wind for the bbox. Note 10 m wind ≠ plume effective wind [S05, S07]. |
| PR-W13 | Wind available to the belief | truth × exp(0.25 · N(0, 1)) | [A] | Reanalysis-style estimate. The belief never sees true wind. |
| PR-W20 | Injected event (`demo.yaml` only) | t = +20 h, source index 0, cloud 0.90 for 12 h, in both truth and forecast | [D] | Golden demo step 5. It's a scripted *environment* change; the *decision* change must emerge from the solver. |

## 8. Planner and solver

| ID | Parameter | Value | Tag | Note |
|---|---|---|---|---|
| PR-O01 | Lookahead per solve | 24 h | [D] | The one-visit-per-source rule applies per solve, so revisits remain possible across solves. |
| PR-O02 | Replan triggers | after each pass; on informative acquisition; on forecast issue | [D] | The current pass is frozen once it starts. |
| PR-O03 | Max visits per source per solve | 1 | [D] | Prevents double-counting EIG (PRD §7.2). |
| PR-O04 | Objective weights | information 1.0; others 0 | [D] | Pure-EIG research baseline (PRD §20). |
| PR-O05 | Integer scale | 10,000 per bit | [D] | Max objective ≈ 20 × 1 bit × 10⁴ = 2×10⁵, far below int64 limits. |
| PR-O06 | Candidate pruning | drop EIG < 0.001 bit | [D] | |
| PR-O07 | Solver limit | `max_deterministic_time` 30 | [D] | Deterministic-time units, not wall clock. A wall-clock cutoff depends on machine load and breaks same-seed replay (Parameter_2 G-01). |
| PR-O08 | Solver mode | `reproducible`: 1 worker, seed = `derive_seed(run seed, "solver", policy, revision)` | [D] | Multi-worker CP-SAT is not run-to-run deterministic. `fast` mode (8 workers, 10 s wall) is UI-only and tagged non-reproducible. |
| PR-O09 | Acquisition options | every 10 s inside a window, max 12, always including the minimum-off-nadir time | [D] | Discrete start times (PRD §20) make slew constraints exact, and the checker can verify them independently. |
| PR-O10 | Utility | `one_step_eig` (default); ablation `brier_reduction_to_next_pass` | [D] | One-step EIG ignores how quickly information decays (episodic τ ≈ 2 h vs ~21 h between pass clusters). The ablation scores the expected Brier reduction until the next pass. |

**Policies (all use the same windows, constraints, checker and belief filter; only selection differs):**

| Policy | Selection |
|---|---|
| `first_feasible` (B1) | Chronological order, greedy insertion. |
| `largest_first` (B2) | Sort by posterior E[Q \| active]; prior median if never observed; greedy. |
| `static_priority` (B3) | EIG computed once at t0, never updated; CP-SAT. |
| `adaptive_eig` (B4, AETHER) | Fresh EIG at every replan; CP-SAT. |
| `greedy_eig` (B5, strong comparator) | Fresh EIG; greedy by EIG. Separates "adaptive" from "optimizer". |

**Scoring fairness:** every policy's run is scored on beliefs from the **identical** filter, so differences come only from which data each policy collected.

## 9. Evaluation

| ID | Parameter | Value | Tag |
|---|---|---|---|
| PR-E01 | Evaluation times | every 6 h from t0 to horizon | [D] |
| PR-E02 | High-impact source | true mean emission rate over the horizon (off time counts as 0) ≥ 278 kg/h. Expressed as a rate, so it scales to h168. | [D] |
| PR-E03 | Corroboration | first time P(Z = z_true) ≥ 0.90 at an evaluation time; right-censored | [D] |
| PR-E04 | Bootstrap | 10,000 paired resamples, 95% percentile CI | [D] |
| PR-E05 | Success criterion | see `experiments/protocol.yaml`; wins on m0 plus ≥ 2 misspecified families after Holm correction; `greedy_eig` comparison reported with equal prominence | [D] |
| PR-E06 | Reference policies | `random_feasible` (lower bound), `oracle` (reads truth; upper bound) | [D] | Gate G4.5: the oracle-minus-random Brier gap must exceed 2 × the seed-to-seed SD on dev seeds, or the scenario can't discriminate between policies. |
| PR-E07 | B1 request stream | Poisson, 1 request per source per 24 h | [A] | Parameter_2 ENG-SIM-006. Same stream for every policy (rng `requests`). |
| PR-E08 | Log-loss probability clip | p clipped to [1e-12, 1 − 1e-12] before ln | [D] | Same value as Parameter_2 ENG-BEL-007. Caps one confidently wrong prediction at −ln(1e-12) ≈ 27.6 nats instead of ∞. |
| PR-E09 | ECE bins | 10 equal-width bins on [0, 1], weighted by count; p = 1 goes in the top bin | [D] | Standard reliability-diagram binning. With ~240 points per run, finer bins would be mostly empty. |
| PR-E10 | High-impact recall cut-off | top k = 5 sources, ranked by Σ_r P(r) · π_r · flux median (planner-side long-run mean rate) at the last evaluation time; ties by source id | [D] | k = 5 is in the metric name (protocol.yaml). The ranking score estimates the same long-run mean rate that PR-E02 thresholds. Alternatives are in `docs/validation-report.md`. |

## 10. Remaining gaps that need a human

| Gap | Who | Blocking? |
|---|---|---|
| NASA Earthdata login (needed to download EMIT V002 fixtures): run `! earthaccess login` or provide `~/.netrc` | You | ING-02 only; everything else uses a synthetic fixture first |
| Exact EMIT V002 GeoJSON property names: not in any public page I found; must be read from a downloaded granule and the ATBD §4.2.5 | ING-02 after download | Parser mapping only |
| Copernicus CDS API key for ERA5 checks (PR-W01, PR-W10) | You | No (P1) |
| Carbon Mapper Terms of Use version and redistribution rights | You / ING-06 | No (P1) |
| Domain sign-off on PR-P10 (including its upper tail σ_ln), PR-P20–22, PR-V11, and the meaning of the EMIT `Emissions Rate Estimate Uncertainty (kg/hr)` field (undefined in the public ATBD v0.2 / User Guide v02, so kept `UNKNOWN`), by someone with methane remote-sensing background | Science reviewer | Before any results are published |

## Added citations (extend PRD §25)

| ID | Source |
|---|---|
| S16 | Cusworth, D. H. et al. (2021) *Intermittency of Large Methane Emitters in the Permian Basin*, ES&T Letters 8(7):567–573. DOI 10.1021/acs.estlett.1c00173 |
| S17 | Carbon Mapper, *Tanager Methane Performance Specifications*: https://carbonmapper.org/articles/tanager-methane-performance-specifications |
| S18 | AMT 2025 Tanager detection-limit study: https://amt.copernicus.org/articles/18/6933/2025/ ; Carbon Mapper IWGGMS presentation (Duren): https://atmosphere.copernicus.eu/sites/default/files/custom-uploads/IWGGMS%2022%20event/Day1/1.06_Duren.pdf |
| S19 | Jacob, D. J. et al. (2016) *Satellite observations of atmospheric methane and their value for quantifying methane emissions*, ACP 16:14371. DOI 10.5194/acp-16-14371-2016 |
| S08 (DOI) | Ayasse et al. (2024) ES&T, DOI 10.1021/acs.est.4c06702 |
