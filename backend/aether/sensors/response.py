"""Virtual sensor response functions (SCI-01). Pure, no I/O, no randomness.

Every function takes the ``SensorProfile`` of the view that calls it: the simulator passes the truth
profile, the belief filter passes the model profile. That is how the m2/m4 families take effect.

Flux and wind arguments accept floats or NumPy arrays (the belief evaluates whole flux grids).
Parameters: PR-V01, PR-V02 (GSD), PR-V10..V13 (POD), PR-V20..V22 (false alarms), PR-V30..V32
(validity) in Implementation/Parameter_Register.md.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray

from aether.config import SensorProfile

_LN_SQRT_2PI = 0.5 * math.log(2.0 * math.pi)


def _check_off_nadir(off_nadir_deg: float) -> float:
    theta = abs(float(off_nadir_deg))
    if not theta < 90.0:
        raise ValueError(f"off-nadir angle must be below 90 deg, got {off_nadir_deg}")
    return theta


def gsd_effective_m(sensor: SensorProfile, off_nadir_deg: float) -> float:
    """Ground sampling distance at a look angle: gsd_nadir / cos(theta)^exponent (PR-V02)."""
    theta = math.radians(_check_off_nadir(off_nadir_deg))
    return sensor.gsd_nadir_m / math.cos(theta) ** sensor.gsd_off_nadir_exponent


def q50_kg_h(sensor: SensorProfile, wind_m_s: ArrayLike, off_nadir_deg: float) -> NDArray | float:
    """Flux with 50 % detection probability, scaled by wind and pixel size (PR-V11..V13).

    Q50 = Q50_ref * (clip(U) / U_ref)^wind_exp * (gsd_eff / gsd_ref)^gsd_exp.
    """
    pod = sensor.pod
    lo, hi = pod.wind_clip_m_s
    u = np.clip(np.asarray(wind_m_s, dtype=float), lo, hi)
    gsd_ratio = gsd_effective_m(sensor, off_nadir_deg) / pod.ref_gsd_m
    out = (
        pod.q50_ref_kg_h
        * (u / pod.ref_wind_m_s) ** pod.wind_scaling_exponent
        * gsd_ratio**pod.gsd_scaling_exponent
    )
    return float(out) if out.ndim == 0 else out


def pod(
    sensor: SensorProfile, q_kg_h: ArrayLike, wind_m_s: ArrayLike, off_nadir_deg: float
) -> NDArray | float:
    """Probability of detecting an active source of flux q in a valid scene (PR-V10).

    POD = 1 / (1 + exp(-k (ln q - ln Q50))) with k = ln 9 / ln(Q90/Q50). POD(0) = 0.
    """
    q = np.asarray(q_kg_h, dtype=float)
    if np.any(q < 0):
        raise ValueError("flux must be non-negative")
    k = sensor.pod.logistic_slope
    ln_q50 = np.log(q50_kg_h(sensor, wind_m_s, off_nadir_deg))
    with np.errstate(divide="ignore"):
        ln_q = np.log(q)  # -inf at q = 0 gives POD exactly 0 below
    with np.errstate(over="ignore"):  # exp overflow -> inf -> POD 0, which is the right limit
        out = 1.0 / (1.0 + np.exp(-k * (ln_q - ln_q50)))
    return float(out) if out.ndim == 0 else out


def p_valid(
    sensor: SensorProfile, cloud_fraction: float, off_nadir_deg: float, max_off_nadir_deg: float
) -> float:
    """Probability a scene is usable for retrieval (PR-V30..V32). Independent of emission state.

    retrieval_success * (1 - cloud) * (1 - penalty * (theta / theta_max)^2). An unusable scene is
    INVALID_ACQUISITION, never a non-detection (PRD 5.5).
    """
    if not 0.0 <= cloud_fraction <= 1.0:
        raise ValueError(f"cloud_fraction must be in [0, 1], got {cloud_fraction}")
    if max_off_nadir_deg <= 0:
        raise ValueError("max_off_nadir_deg must be positive")
    theta = _check_off_nadir(off_nadir_deg)
    if theta > max_off_nadir_deg + 1e-9:
        raise ValueError(f"off-nadir {theta} deg exceeds the limit {max_off_nadir_deg} deg")
    v = sensor.validity
    geometry = 1.0 - v.off_nadir_quality_penalty * (theta / max_off_nadir_deg) ** 2
    return float(min(1.0, max(0.0, v.retrieval_success_prob * (1.0 - cloud_fraction) * geometry)))


def p_detect(
    sensor: SensorProfile,
    active: bool,
    q_kg_h: ArrayLike,
    wind_m_s: ArrayLike,
    off_nadir_deg: float,
) -> NDArray | float:
    """P(DETECTION | valid scene, state) (PR-V22): one definition for simulator and belief.

    Active: POD(q). Inactive: the false-alarm probability (PR-V20). No false-alarm term is added for
    active sources.
    """
    if active:
        return pod(sensor, q_kg_h, wind_m_s, off_nadir_deg)
    return float(sensor.false_positive_prob)


def false_positive_flux_logpdf(sensor: SensorProfile, ln_measured: ArrayLike) -> NDArray | float:
    """Log density, per unit ln-flux, of the flux reported by a false alarm (PR-V21).

    Normal in ln-flux, so it has the same units as the active-source measurement density and
    posteriors do not depend on the flux unit. The simulator samples false-alarm fluxes from it.
    """
    fp = sensor.false_positive_flux
    z = (np.asarray(ln_measured, dtype=float) - math.log(fp.median_kg_h)) / fp.sigma_ln
    out = -0.5 * z * z - math.log(fp.sigma_ln) - _LN_SQRT_2PI
    return float(out) if out.ndim == 0 else out
