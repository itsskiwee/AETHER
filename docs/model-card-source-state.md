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

The publisher's primary article page and abstract are accessible. The methods and results describe persistence as `f = M/N`: detected plume count divided by overflight count at a source. The summary includes 1,100 sources with at least three overflights (average eight), and reports mean persistence 0.26; sources are initially identified because they produced a detected plume. The paper also reports persistence falling between one and three overflights and stabilizing within 1σ of 0.26 for N ≥ 3. This is a selected, detection-conditioned sample, not a direct estimate of the unconditional stationary active fraction of all facilities. The paper's definition does **not** support treating 0.26 as a direct calibration target for the regime-mixture π.

| Fact | Value | Source |
|---|---|---|
| Survey | ~55 000–57 000 km² of the Permian, Sep–Nov 2019, airborne imaging spectrometers | EGU21-13824 abstract; NASA/JPL release (2 Jun 2021) |
| Average persistence | **26 %** for sources with ≥3 airborne overflights | Cusworth et al. publisher article page, Methods and Results |
| Sources seen on ≥ 3 flights | 1 100; most persistent class 123 (plumes on 50–100 % of revisits, ~29 % of detected CH₄); next 258 (~23 %); remaining ~2/3 (~48 %) | NASA/JPL release |
| Heavy tail | 20 % of facilities emit 60 % of the point-source budget | EGU21-13824 abstract |
| Detection threshold of the campaign | ~10 kg/h ("super-emitter" definition) | NASA/JPL release |

Primary source: [Cusworth et al. 2021, ACS publisher article](https://pubs.acs.org/doi/10.1021/acs.estlett.1c00173). Supporting overview: https://www.jpl.nasa.gov/news/study-identifies-methane-super-emitters-in-largest-us-oilfield/.

### Finding: the register's consistency argument doesn't hold as written

The register's former argument that "mean π = 0.29 is consistent with ~0.26" compared a population-average activity fraction with a detection-conditioned statistic. The publisher's article confirms that persistence is M/N over overflights for detected source locations, with inclusion requiring at least three overflights. The selection and finite revisit schedules mean the observed average is not the unconditional π. It is also not a simple `π × POD` statistic: the campaign used source-specific detection counts and revisit denominators, and the published methods do not furnish a single effective POD or uniform revisit schedule with which to invert the value.

Model analogue (exact enumeration over detection histories, POD = 1 because the airborne limit of ~10 kg/h is far below the 300 kg/h median; `persistence_check.py`, reproduced below):

| Revisits per source | Spacing | Mean detections/revisits, sources with ≥ 1 detection | Same, ≥ 3 detections |
|---|---|---|---|
| 3 | 24 h | 0.59 | 1.00 |
| 5 | 24 h | 0.48 | 0.80 |
| 5 | 72 h | 0.47 | 0.78 |
| 8 | 24 h | 0.42 | 0.61 |

This enumeration is a **sensitivity diagnostic**, not a reproduction of the study: it assumes regular revisit spacings, a single detection probability, and a source population drawn from the AETHER regime mixture. It cannot be used to infer that the paper's value implies a particular AETHER π. It does show that the current model produces higher detected revisit fractions in these simplified cases.

Options:

| Option | Effect | Risk |
|---|---|---|
| (a) Keep PR-P20..P22 as scenario assumptions and report the 0.26 comparison as non-like-for-like | Does not silently convert a detection statistic into unconditional activity; no benchmark-scope change | Does not validate those regime parameters |
| (b) Recalibrate the regimes to reproduce the study's selected-source M/N statistic | Could provide a targeted phenomenological match | Requires matching source selection, overflight counts/timing, detectability and source distribution; 0.26 alone does not identify those parameters |
| (c) Add an alternate persistence family after defining a separate calibration target | Makes sensitivity explicit | Changes benchmark scope and multiplicity family; requires approval and a protocol amendment |

**Current recommendation (17 Oct 2026):** retain the existing regime values and benchmark scope pending approval; describe them as unverified assumptions and do not claim they are calibrated to Cusworth's 0.26. Keep the existing m1 sensitivity family as defined, without treating it as a fitted alternative. A dedicated recalibration or new family is a separate protocol decision. The model card's previous claim that the selection-adjusted value was roughly 0.42–0.59 is superseded as a calibration interpretation; retain that enumeration only as a toy-model diagnostic, not evidence of a twofold discrepancy.

**Approval needed:** Should the benchmark retain its existing m0 regime assumptions and scope (recommended), or should L1/L3 define a new calibrated scenario/family and update the protocol before lock? No parameter or benchmark scope has been changed here. PR-P20..P22 remain **[A]**.

## Truncated flux prior implementation evidence

`simulation/truth.py` draws each source's static flux with an inverse-CDF transform between the
truncated lognormal CDF limits. The belief integrates the same truncated density into its log-flux
grid (PR-B06). This removes the endpoint atoms caused by clipping. Deterministic acceptance
evidence is in `tests/unit/test_simulation_science.py`: a 5,000-source keyed sample is checked with
a one-sample KS test against the truncated CDF, endpoint equality is rejected, repeated seeds are
compared exactly, and reordering source inputs must not change a source's draw. These tests have
been added but could not be executed in this environment because pytest is not installed.

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
