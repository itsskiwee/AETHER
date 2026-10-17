# Model card: source-state model and belief filter

**Owner:** L2 Science model · **Code:** `backend/aether/belief/` · **Model version:** `belief-hmm3-lngrid-v1`
**Status:** research assumption. Parameters are anchored to Permian literature but not fitted to it.

## Intended use

Represent what the planner believes about each source hypothesis (provenance `MODEL_INFERENCE`): its persistence regime, whether it is emitting in the current hour, and its on-rate. This belief drives the planner's utilities (EIG, Brier-reduction ablation) and the beliefs that L3 scores against hidden truth.

**Not for:** statements about whether a real facility is or was emitting.

## Model

- **Regime** r ∈ {PERSISTENT, INTERMITTENT, EPISODIC}, static per source, prior weights 0.15 / 0.45 / 0.40 (PR-P20..P22).
- **Activity** z ∈ {0, 1} per 1 h bin, following each regime's 2-state Markov chain with `p(on→off) = 1/mean_on`, `p(off→on) = 1/mean_off`. It starts at the regime's stationary fraction (PR-R02).
- **On-rate** Q, static per source, lognormal median 300 kg/h, σ_ln 1.1, truncated to [30, 30 000] (PR-P10), on a 64-point ln grid from 10 to 50 000 kg/h (PR-B01). Each bin's prior mass is integrated exactly (PR-B06).
- **Belief** = normalized tensor P[r, z, g]. `predict` applies the hourly transition matrices per regime; Q and r don't change. `update` multiplies by the observation likelihood (observation model card) and renormalizes in log space.
- **Missing data:** `INVALID_ACQUISITION` and `NOT_OBSERVED` return the identical object. A pure time step sets `received_new_evidence = False`.
- **Summaries:** `p_active` (current hour); regime marginals; the median, 90 % interval (5th–95th percentile, linear CDF in ln-flux within bins) and mean of Q. The flux interval refers to the **on-rate Q**, the source's emission rate when active. It is not the instantaneous unconditional rate E[Z·q].

## Utilities

- `expected_info_gain_bits`: one-step reduction of binary activity entropy at the acquisition time over {DETECTION, VALID_NON_DETECTION, INVALID}. Closed form; in [0, H(p)]; 0 when p_valid = 0. A plug-in Monte Carlo mutual information on 10⁵ samples agrees within 0.005 bit (`test_eig.py`).
- `expected_brier_reduction` (PR-O10 ablation): expected reduction of Σ p_τ(1−p_τ) over evaluation times τ in [acquisition, next pass). It values regime information that outlasts the current state. A persistent source scores more than 5× an episodic one in the test case; one-step EIG can't see that difference.

## SCI-08 parameter verification

### Cusworth et al. 2021 [S16]: what could be checked

The journal paper (ES&T Letters 8(7):567–573, DOI 10.1021/acs.estlett.1c00173) is paywalled (HTTP 403 from this environment). Verified from public sources:

| Fact | Value | Source |
|---|---|---|
| Survey | ~55 000–57 000 km² of the Permian, Sep–Nov 2019, airborne imaging spectrometers | EGU21-13824 abstract; NASA/JPL release (2 Jun 2021) |
| Average persistence | **26 %** | EGU21-13824 abstract ("CH4 sources exhibited 26% persistence on average"); the journal text was **not** checked |
| Sources seen on ≥ 3 flights | 1 100; most persistent class 123 (plumes on 50–100 % of revisits, ~29 % of detected CH₄); next 258 (~23 %); remaining ~2/3 (~48 %) | NASA/JPL release |
| Heavy tail | 20 % of facilities emit 60 % of the point-source budget | EGU21-13824 abstract |
| Detection threshold of the campaign | ~10 kg/h ("super-emitter" definition) | NASA/JPL release |

Links: https://meetingorganizer.copernicus.org/EGU21/EGU21-13824.html · https://www.jpl.nasa.gov/news/study-identifies-methane-super-emitters-in-largest-us-oilfield/

### Finding: the register's consistency argument doesn't hold as written

The register (§4) argues "detection persistence ≈ π × POD < π, so a modelled mean π of 0.29 is consistent with ~0.26 observed." That compares a population-average activity fraction with a statistic that can only be computed **for sources the survey detected at least once**. The selection inflates the observed fraction.

Model analogue (exact enumeration over detection histories, POD = 1 because the airborne limit of ~10 kg/h is far below the 300 kg/h median; `persistence_check.py`, reproduced below):

| Revisits per source | Spacing | Mean detections/revisits, sources with ≥ 1 detection | Same, ≥ 3 detections |
|---|---|---|---|
| 3 | 24 h | 0.59 | 1.00 |
| 5 | 24 h | 0.48 | 0.80 |
| 5 | 72 h | 0.47 | 0.78 |
| 8 | 24 h | 0.42 | 0.61 |

So under the most likely reading of "persistence", the PR-P20..P22 regimes imply roughly **0.42–0.59**, not ~0.26. Matching 26 % would need far less activity: more episodic weight and/or shorter on-periods. The unconditional mean π of 0.29 only matches if Cusworth's 26 % is averaged over every surveyed site, including never-detected ones. The abstract's wording suggests it isn't.

Options:

| Option | Effect | Risk |
|---|---|---|
| (a) Keep PR-P20..P22 and correct the register's claim to "not verified; may overstate persistence by ~2×" | No code change; honest | Benchmark may be more persistent (easier for adaptive revisits) than the Permian |
| (b) Recalibrate the regimes so the selected-source statistic ≈ 0.26 for the paper's revisit counts | Literature-consistent | Needs the paper's exact definition and revisit distribution (paywalled). Lower persistence reduces discriminability (gate G4.5) |
| (c) Keep (a) as m0 and add a lower-persistence family | Shows sensitivity directly | One more family in the multiplicity correction |

**Decision (17 Oct 2026, L1 + L2):** (a) done (Register §4 "known mismatch"; PR-P20..P22 marked "[A] may overstate persistence (SCI-08)"), (c) adopted with `m1_persistence_wrong` as the lower-persistence sensitivity family, (b) deferred until the paper's methods have been read. L1 reproduced the numbers independently and added: m1 gives 0.42 at POD = 1 and 0.33 at POD = 0.6; with no persistent sources at all, 0.36 / 0.29. Reaching ~0.26 therefore needs both less persistence **and** an airborne POD below 1, not just a weight change. Whether to add a calibrated family (m5) before the protocol lock is with the user and L3.

**Original recommendation:** (a) now, plus (c). The existing `m1_persistence_wrong` family already shifts mass toward EPISODIC in truth, which covers part of (c). Do (b) only after someone reads the paper's methods section. This is a judgment call for L1/L3 and the user, so I haven't changed any config value. PR-P20..P22 stay **[A]**.

### EMIT fixture comparison (flux prior PR-P10)

**Not possible yet.** `data/fixtures/` holds only fabricated, EMIT-shaped parser fixtures (`EXAMPLE_ONLY_NOT_SOURCE_VERIFIED`). Their rates are invented and must not be compared with the prior. ING-02 (real V002 Permian granules, needs an Earthdata login) is the dependency. Even then, EMIT detects only above ~1 t/h at 3 m/s [S08], so the comparison is limited to the upper tail. Planned check: P(Q > 1000 kg/h) under the prior is 1 − Φ((ln 1000 − ln 300)/1.1) = 1 − Φ(1.09) ≈ 0.14. That's the fraction to compare with the EMIT-detectable share of a complete aircraft inventory, not with EMIT rates alone.

## Limitations

1. Regime is static over the horizon (72–168 h). Real operations change regime (repairs, new wells).
2. Sources are independent. Shared infrastructure (gathering lines) correlates nearby sources (Parameter_2, PRD §16 P1).
3. Hourly flux variability is i.i.d. Real flux has autocorrelation and diurnal patterns.
4. The 1 h time bin is the shortest resolvable change. EPISODIC events (mean 3 h) are near that limit.
5. The beliefs are only as good as the regime parameters, which are unverified (above).

## Reproduction of the persistence check

```python
import itertools, numpy as np
regimes = {"PERSISTENT": (0.15, 240, 48), "INTERMITTENT": (0.45, 12, 24), "EPISODIC": (0.40, 3, 72)}
def mean_persistence(n_visits, spacing_h, min_det=1):
    num = den = 0.0
    for w, on, off in regimes.values():
        a, b = 1 / on, 1 / off
        T = np.linalg.matrix_power(np.array([[1 - b, b], [a, 1 - a]]), spacing_h)
        pi = b / (a + b)
        for hist in itertools.product((0, 1), repeat=n_visits):
            k = sum(hist)
            if k < min_det:
                continue
            p = pi if hist[0] else 1 - pi
            for x, y in zip(hist, hist[1:]):
                p *= T[x, y]
            num += w * p * k / n_visits
            den += w * p
    return num / den
```

## Sign-off

Not reviewed by a domain scientist. Required before publication (Register §10).
