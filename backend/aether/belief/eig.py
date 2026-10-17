"""Expected value of a planned observation (SCI-06, PR-O10). Model view only.

Both utilities are closed form over the outcome categories {DETECTION, VALID_NON_DETECTION,
INVALID_ACQUISITION}. The measured flux of a detection also carries a little information about z
(false alarms report fluxes near threshold), which the category form ignores, so these are
conservative (lower-bound) values. PR-B05.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import numpy as np

from aether.belief.filter import SourceBelief, binary_entropy_bits
from aether.config import SensorProfile
from aether.sensors import p_valid


def _outcome_split(
    belief: SourceBelief,
    *,
    sensor: SensorProfile,
    wind_forecast_m_s: float,
    off_nadir_deg: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Unnormalized (R, 2, G) tensors for detection and non-detection, given a valid scene."""
    pod_g = belief.model.pod_active(sensor, wind_forecast_m_s, off_nadir_deg)
    p_det = np.stack([np.full_like(pod_g, sensor.false_positive_prob), pod_g])  # (2, G)
    det = belief.tensor * p_det[None, :, :]
    return det, belief.tensor - det


def _p_valid(sensor, cloud_forecast, off_nadir_deg, max_off_nadir_deg) -> float:
    return p_valid(sensor, cloud_forecast, off_nadir_deg, max_off_nadir_deg)


def expected_info_gain_bits(
    belief: SourceBelief,
    *,
    at_utc: datetime,
    sensor: SensorProfile,
    wind_forecast_m_s: float,
    cloud_forecast: float,
    off_nadir_deg: float,
    max_off_nadir_deg: float,
) -> float:
    """One-step expected reduction in binary activity entropy at ``at_utc``, in bits (PRD 7.1).

    EIG = H(p) - sum_y P(y) H(p | y). INVALID (probability 1 - p_valid) leaves H(p) unchanged, so
    EIG = p_valid * [H(p) - P(det|valid) H(p|det) - P(nd|valid) H(p|nd)]. Always in [0, H(p)].
    """
    b = belief.predict(at_utc)
    pv = _p_valid(sensor, cloud_forecast, off_nadir_deg, max_off_nadir_deg)
    if pv == 0.0:
        return 0.0
    det, nd = _outcome_split(
        b, sensor=sensor, wind_forecast_m_s=wind_forecast_m_s, off_nadir_deg=off_nadir_deg
    )
    p = b.p_active()
    gain = binary_entropy_bits(p)
    for part in (det, nd):
        mass = float(part.sum())
        if mass > 0.0:
            gain -= mass * binary_entropy_bits(float(part[:, 1, :].sum()) / mass)
    return float(min(max(pv * gain, 0.0), binary_entropy_bits(p)))


def expected_brier_reduction(
    belief: SourceBelief,
    *,
    at_utc: datetime,
    eval_times: Iterable[datetime],
    next_pass_utc: datetime | None,
    sensor: SensorProfile,
    wind_forecast_m_s: float,
    cloud_forecast: float,
    off_nadir_deg: float,
    max_off_nadir_deg: float,
) -> float:
    """Expected reduction of summed Brier error of p_active over evaluation times (PR-O10 ablation).

    Covers evaluation times tau with at_utc <= tau < next_pass_utc (all later times if None). Under
    the model, the expected Brier error of belief p at tau is p_tau (1 - p_tau), so the reduction is
    sum_tau [p_tau(1 - p_tau) - sum_y P(y) p_tau^y (1 - p_tau^y)]. Information about episodic
    sources decays within hours, which one-step EIG ignores; regime information persists and
    counts here.
    """
    b = belief.predict(at_utc)
    taus = sorted(
        t for t in eval_times if t >= at_utc and (next_pass_utc is None or t < next_pass_utc)
    )
    pv = _p_valid(sensor, cloud_forecast, off_nadir_deg, max_off_nadir_deg)
    if not taus or pv == 0.0:
        return 0.0
    det, nd = _outcome_split(
        b, sensor=sensor, wind_forecast_m_s=wind_forecast_m_s, off_nadir_deg=off_nadir_deg
    )
    m = b.model
    total = 0.0
    for tau in taus:
        steps = m.step_matrices(m.hour_bin(tau) - m.hour_bin(at_utc))

        def p_at(t: np.ndarray, steps: np.ndarray = steps) -> float:
            moved = np.einsum("rab,rag->rbg", steps, t)
            return float(moved[:, 1, :].sum() / moved.sum())

        p0 = p_at(b.tensor)
        expected_after = 0.0
        for part in (det, nd):
            mass = float(part.sum())
            if mass > 0.0:
                py = p_at(part)
                expected_after += mass * py * (1.0 - py)
        total += p0 * (1.0 - p0) - expected_after
    return float(max(pv * total, 0.0))
