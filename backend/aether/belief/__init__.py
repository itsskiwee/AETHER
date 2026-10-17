"""Lane L2 (science). Source belief filter and expected information gain. MODEL_INFERENCE only.

Belief per source = a normalized tensor P[regime r, state z, ln-flux grid index g] (3 x 2 x G).
Regime is static per source; z follows the regime's 2-state Markov chain on 1 h steps; flux is
static per source (hourly variability is folded into the measurement noise).

Interface (tasks SCI-03..SCI-07):

    class SourceBelief:
        @classmethod
        def prior(cls, source_id, cfg: ScenarioConfig) -> SourceBelief
            regime weights x stationary p_active x lognormal flux prior on the grid
        def predict(self, to_utc) -> SourceBelief            # Markov step(s); no evidence
        def update(self, acq: SimulatedAcquisition, *, sensor) -> SourceBelief
            Uses acq.wind_estimate_m_s (never true wind) and acq.off_nadir_deg.
            DETECTION, z=1: lik = pod(q) * N(ln meas; ln q, sigma_eff) / 1   (a density in ln-flux)
            DETECTION, z=0: lik = fp * f_FP(ln meas)                          (same units: density)
            VALID_NON_DETECTION: lik = 1 - P(det|z,q)
            INVALID_ACQUISITION / NOT_OBSERVED: returns self unchanged (bit-identical tensor)
            sigma_eff = sqrt(flux_measurement.sigma_ln**2 + sources.hourly_variability_sigma_ln**2)
            because the belief holds flux static while truth varies hourly (keeps m0
            well specified).
            Unit-invariance test: rescaling every flux by a constant leaves p_active unchanged.
        def p_active(self) -> float
        def entropy_bits(self) -> float                       # binary H(p_active)
        def snapshot(self) -> BeliefSnapshot

    expected_info_gain_bits(belief, *, at_utc, sensor, wind_forecast_m_s, cloud_forecast,
                            off_nadir_deg, max_off_nadir_deg) -> float
        Closed form over outcomes {DETECTION, VALID_NON_DETECTION, INVALID}:
        EIG = H(p) - sum_y P(y) H(p | y), with P(INVALID) = 1 - p_valid contributing H(p).
        Non-negative up to 1e-12. Must use the belief predicted to at_utc.

    expected_brier_reduction(belief, *, at_utc, eval_times, next_pass_utc, ...) -> float   (PR-O10)
        Ablation utility: expected reduction of summed squared error of p_active over the
        evaluation times between at_utc and next_pass_utc. Captures that information about
        episodic sources decays within hours while regime information lasts.

Implementation notes (L2): likelihoods marginalize hourly flux variability and wind-estimate
error exactly by Gauss-Hermite quadrature (filter.py docstring, PR-B03/B04); with constant POD this
is the sigma_eff form above. EIG and the Brier ablation use outcome categories only (PR-B05).

Import rule: this package must never import aether.simulation or aether.evaluation.
"""

from aether.belief.eig import expected_brier_reduction, expected_info_gain_bits
from aether.belief.filter import MODEL_VERSION, BeliefModel, SourceBelief, binary_entropy_bits

__all__ = [
    "MODEL_VERSION",
    "BeliefModel",
    "SourceBelief",
    "binary_entropy_bits",
    "expected_brier_reduction",
    "expected_info_gain_bits",
]
