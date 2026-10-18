# Model card: observation model (virtual sensor VS-A)

**Owner:** L2 Science model · **Code:** `backend/aether/sensors/response.py`, likelihoods in `backend/aether/belief/filter.py` · **Model version:** `belief-hmm3-lngrid-v1`
**Status:** `SIMULATED_PROFILE`. Every number is a scenario assumption anchored to public Tanager-class figures. This is **not** a Tanager, EMIT or vendor specification and has not been calibrated against any real instrument.

## Intended use

Generate simulated acquisition outcomes (L6, truth view) and compute the likelihood of those outcomes in the belief filter (L2, model view) for a research benchmark of observation-scheduling policies. Both sides call the **same functions**, each with its own `SensorProfile`. That's how the misspecification families m2 (POD optimistic) and m4 (false positives) take effect.

**Not for:** claims about any real sensor's detection limit, real-world non-detection interpretation, or emission estimation from real data.

## Model

For one acquisition of a source at off-nadir angle θ, with wind U and current flux q:

| Step | Definition | Register |
|---|---|---|
| Effective pixel size | `gsd_eff = gsd_nadir / cos(θ)^n` | PR-V01, PR-V02 |
| 50 % detection flux | `Q50 = Q50_ref · (clip(U, 1, 10)/U_ref)^1 · (gsd_eff/gsd_ref)^1` | PR-V11..V13 |
| Probability of detection (active, valid scene) | `POD = 1/(1+exp(−k(ln q − ln Q50)))`, `k = ln 9 / ln(Q90/Q50) = 3.17`; `POD(0) = 0` | PR-V10, PR-V11 |
| Scene validity | `p_valid = 0.95 · (1 − cloud) · (1 − 0.25 (θ/θ_max)²)` | PR-V30..V32 |
| Detection definition | `P(det | active) = POD(q)`; `P(det | inactive) = 0.02` | PR-V20, PR-V22 |
| False-alarm reported flux | lognormal, median 100 kg/h, σ_ln 0.5 (a density in ln-flux) | PR-V21 |
| Measured flux (true detection) | `ln m = ln q + 0.35 ζ`, ζ ~ N(0, 1) | PR-V40 |
| Data / energy per scene | 306 MB / 0.2 Wh | PR-V50, PR-V51 |

Outcomes: an invalid scene is `INVALID_ACQUISITION` and carries **no** emission evidence. A valid scene is `DETECTION` or `VALID_NON_DETECTION`.

### How the belief uses it (likelihoods)

The belief tracks the source's static on-rate Q, but truth uses `q = Q·exp(ε)` hourly (PR-P11, σ = 0.30). The belief also sees only a wind estimate `U_est = U_true·exp(0.25 N)` (PR-W13). Both nuisance terms are integrated out exactly rather than ignored:

- **Valid non-detection:** `1 − E_ε,δ[POD(Q e^ε; U_est e^δ)]` if active; `1 − 0.02` if inactive.
- **Detection with measured flux m:** active `N(ln m − ln Q; 0, σ_eff) · E[POD | ε ~ N(μ*, s*)]`, with `σ_eff = √(0.35² + 0.30²) = 0.46` (PR-V41). Inactive `0.02 · f_FP(ln m)`. Both are densities per unit ln-flux, so posteriors don't depend on the flux unit (tested by rescaling kg/h → kg/s).
- Gauss–Hermite quadrature, 16 nodes per nuisance dimension (PR-B03). Wind error uses a flat-prior inversion (PR-B04).
- `p_valid` doesn't depend on the emission state, so it cancels in the update. It only enters planning utilities.

## Evaluation (tests in `backend/tests/unit/`)

| Property | Test |
|---|---|
| POD(Q50) = 0.5, POD(Q90) = 0.9 at reference; POD(0) = 0 | `test_sensors.py::test_pod_anchors_at_reference`, `test_pod_of_zero_flux_is_zero` |
| POD monotone in flux; falls with wind and off-nadir angle | Hypothesis tests in `test_sensors.py` |
| p_valid ∈ [0, 1]; cloud 1 → 0; angle above limit rejected | `test_p_valid_*` |
| False-alarm density integrates to 1 in ln-flux | `test_false_positive_density_normalizes_in_ln_flux` |
| Likelihoods match hand-computed closed forms to 1e-12 | `test_belief.py::test_*_matches_hand_computed_fixture` |
| Unit invariance | `test_posterior_does_not_depend_on_flux_units` |
| Self-consistency: posteriors are calibrated when data come from the model | `test_one_observation_calibration_under_the_model` (3000 sources, reliability bins within 3 SE) |

## Limitations and known blind spots

1. **Uncalibrated.** POD anchors come from public Tanager-1 specification and detection-limit studies [S17, S18]; the wind and pixel scaling comes from Jacob et al. 2016 [S19]. Real POD depends also on surface albedo, aerosol, solar zenith and retrieval algorithm. None of these are modelled (Parameter_2 ENG-SEN-008 is P1).
2. **Wind error processes are currently conflated in planning.** PR-W13 is the acquisition-time analysis estimate error used by the posterior filter. Synthetic forecasts have a separate lead-dependent truth error (currently hard-coded in `weather/synthetic.py`), but candidate utilities use forecast point values and reuse PR-W13 as their wind quadrature. This makes planned information conditional on a noisy analysis-style estimate rather than on the forecast's lead-dependent uncertainty. The two processes need separate configurable truth and model assumptions; proposed parameters are pending L1 schema/register integration. The filter's flat-prior inversion also ignores the wind climatology and [1, 12] m/s truth clip.
3. **Same-hour repeats.** Two acquisitions of one source within one hour share truth's ε. The belief treats them as independent, which slightly overweights them. This is rare with the current phasing.
4. **False alarms** are spatially and temporally independent. Real false positives cluster on bright or heterogeneous surfaces, so a fixed rate understates repeat false alarms at one site.
5. **Measurement error** is lognormal with constant σ. Real IME-method error grows at low wind and for small plumes [S07]. A wind-dependent version is P1.
6. **Category-only utilities.** EIG ignores the information in the measured flux value (PR-B05), so it is a lower bound.

## Open decisions (options + recommendation)

| Decision | Options | Recommendation |
|---|---|---|
| Wind error in the belief | (a) ignore, (b) flat-prior inversion (current), (c) full Bayesian with PR-W10 prior and clip | (b) for P0. It fixes most of the m0 miscalibration from (a); (c) once L6's wind model is frozen. |
| Flux-prior form vs truth | truth currently clips at [30, 30000] kg/h, while the belief and PR-P10 truncate | Truth should truncate (rejection sampling); raised with L6 via L1. Logged as PR-B06. |

## Sign-off

Not reviewed by a methane remote-sensing scientist (Register §10). Required before any results are published.
