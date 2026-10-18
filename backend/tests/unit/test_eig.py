"""SCI-06 and PR-O10: expected information gain and the Brier-reduction ablation."""

import math
from datetime import timedelta

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from aether.belief import (
    SourceBelief,
    binary_entropy_bits,
    expected_brier_reduction,
    expected_info_gain_bits,
)
from aether.config import load_scenario
from aether.contracts.enums import ObservationOutcome as O
from aether.contracts.models import SimulatedAcquisition
from aether.sensors import p_valid, pod

SENSOR_ID = "vs_a_point_source"


@pytest.fixture(scope="module")
def cfg(base_config_path):
    return load_scenario(base_config_path).model


def _at(cfg, hours):
    return cfg.simulation_epoch_utc + timedelta(hours=hours)


def _eig(cfg, belief, hours, *, wind=4.0, cloud=0.3, theta=10.0):
    return expected_info_gain_bits(
        belief,
        at_utc=_at(cfg, hours),
        sensor=cfg.sensors[SENSOR_ID],
        wind_forecast_m_s=wind,
        cloud_forecast=cloud,
        off_nadir_deg=theta,
        max_off_nadir_deg=40.0,
    )


def _detected(cfg, flux=400.0):
    acq = SimulatedAcquisition(
        id="a",
        option_id="w#0",
        window_id="w",
        source_id="s0",
        spacecraft_id="vsat_a",
        sensor_id=SENSOR_ID,
        time_utc=_at(cfg, 18),
        outcome=O.DETECTION,
        measured_flux_kg_h=flux,
        off_nadir_deg=5.0,
        wind_estimate_m_s=4.0,
        scene_cloud_fraction=0.0,
        rng_key="t",
    )
    return SourceBelief.prior("s0", cfg).update(acq, sensor=cfg.sensors[SENSOR_ID])


@settings(max_examples=60, deadline=None)
@given(
    hours=st.floats(18.0, 70.0),
    wind=st.floats(0.5, 15.0),
    cloud=st.floats(0.0, 1.0),
    theta=st.floats(0.0, 40.0),
    detected=st.booleans(),
)
def test_eig_bounded_by_entropy(cfg, hours, wind, cloud, theta, detected):
    b = _detected(cfg) if detected else SourceBelief.prior("s0", cfg)
    eig = _eig(cfg, b, hours, wind=wind, cloud=cloud, theta=theta)
    assert -1e-12 <= eig <= b.predict(_at(cfg, hours)).entropy_bits() + 1e-12


def test_eig_zero_when_scene_cannot_be_valid(cfg):
    assert _eig(cfg, SourceBelief.prior("s0", cfg), 20.0, cloud=1.0) == 0.0


def test_eig_uses_belief_predicted_to_acquisition_time(cfg):
    b = _detected(cfg)
    assert _eig(cfg, b, 30.0) == _eig(cfg, b.predict(_at(cfg, 30.0)), 30.0)
    # The detection's information decays: the same observation is worth more later.
    assert _eig(cfg, b, 19.0) < _eig(cfg, b, 60.0)


def test_eig_matches_monte_carlo_mutual_information(cfg):
    """Plug-in I(Z; Y) from 1e5 samples of the generative process vs the closed form."""
    s = cfg.sensors[SENSOR_ID]
    b = SourceBelief.prior("s0", cfg).predict(_at(cfg, 20))
    m = b.model
    wind, cloud, theta = 4.0, 0.3, 12.0
    rng = np.random.default_rng(7)
    n = 100_000
    flat = b.tensor.reshape(-1)
    idx = rng.choice(flat.size, size=n, p=flat / flat.sum())
    _, z, g = np.unravel_index(idx, b.tensor.shape)
    valid = rng.random(n) < p_valid(s, cloud, theta, 40.0)
    q = np.exp(m.ln_q[g] + m.sigma_hourly_ln * rng.normal(size=n))
    wind_true = wind * np.exp(m.wind_sigma_ln * rng.normal(size=n))
    p_det = np.where(z == 1, pod(s, q, wind_true, theta), s.false_positive_prob)
    det = rng.random(n) < p_det
    y = np.where(~valid, 2, np.where(det, 0, 1))
    joint = np.zeros((2, 3))
    np.add.at(joint, (z, y), 1.0)
    joint /= n
    pz, py = joint.sum(1, keepdims=True), joint.sum(0, keepdims=True)
    nz = joint > 0
    mi = float((joint[nz] * np.log2(joint[nz] / (pz @ py)[nz])).sum())
    assert _eig(cfg, b, 20.0, wind=wind, cloud=cloud, theta=theta) == pytest.approx(mi, abs=0.005)


def test_binary_entropy():
    assert binary_entropy_bits(0.0) == binary_entropy_bits(1.0) == 0.0
    assert binary_entropy_bits(0.5) == pytest.approx(1.0)
    assert binary_entropy_bits(0.2) == pytest.approx(-(0.2 * math.log2(0.2) + 0.8 * math.log2(0.8)))


# --- PR-O10 ablation ------------------------------------------------------------------------


def _brier(cfg, belief, at_h, evals_h, next_pass_h, **kw):
    return expected_brier_reduction(
        belief,
        at_utc=_at(cfg, at_h),
        eval_times=[_at(cfg, h) for h in evals_h],
        next_pass_utc=None if next_pass_h is None else _at(cfg, next_pass_h),
        sensor=cfg.sensors[SENSOR_ID],
        wind_forecast_m_s=kw.get("wind", 4.0),
        cloud_forecast=kw.get("cloud", 0.3),
        off_nadir_deg=10.0,
        max_off_nadir_deg=40.0,
    )


def _one_regime(cfg, index):
    regime = cfg.sources.regimes[index].model_copy(update={"weight": 1.0})
    sources = cfg.sources.model_copy(update={"regimes": (regime,)})
    return cfg.model_copy(update={"sources": sources})


def test_brier_reduction_basic_properties(cfg):
    b = SourceBelief.prior("s0", cfg)
    evals = [18, 24, 30, 36]
    assert _brier(cfg, b, 18, evals, 40) > 0.0
    assert _brier(cfg, b, 18, evals, 40, cloud=1.0) == 0.0
    assert _brier(cfg, b, 18, [6, 12], 40) == 0.0  # no evaluation time in [at, next pass)
    assert _brier(cfg, b, 18, evals, 25) < _brier(cfg, b, 18, evals, 40)


def test_brier_reduction_values_persistent_over_episodic(cfg):
    """Information about an episodic source is gone by the next evaluation times; a persistent
    source's is not. One-step EIG cannot see this difference."""
    evals = [24, 30, 36]
    per = _one_regime(cfg, 0)
    epi = _one_regime(cfg, 2)
    r_per = _brier(per, SourceBelief.prior("s0", per), 18, evals, 40)
    r_epi = _brier(epi, SourceBelief.prior("s0", epi), 18, evals, 40)
    assert r_per > 5 * r_epi


def test_brier_reduction_matches_independent_enumeration_oracle(cfg):
    """Enumerate each model state and category, then propagate each posterior to eval times."""
    b = SourceBelief.prior("s0", cfg).predict(_at(cfg, 18))
    sensor = cfg.sensors[SENSOR_ID]
    wind, cloud, theta = 4.0, 0.3, 10.0
    at_h, eval_h, next_h = 18, (18, 24, 30), 36
    pv = p_valid(sensor, cloud, theta, 40.0)
    pod_grid = b.model.pod_active(sensor, wind, theta)
    p_detection = np.stack([np.full_like(pod_grid, sensor.false_positive_prob), pod_grid], axis=0)
    category_tensors = []
    for likelihood in (p_detection, 1.0 - p_detection):
        category_tensors.append(b.tensor * likelihood[None, :, :])

    oracle = 0.0
    for tau_h in eval_h:
        steps = b.model.step_matrices(tau_h - at_h)
        baseline = np.einsum("rab,rag->rbg", steps, b.tensor)
        p0 = float(baseline[:, 1, :].sum() / baseline.sum())
        expected_risk = 0.0
        for category, likelihood in enumerate((p_detection, 1.0 - p_detection)):
            mass = 0.0
            active_mass = 0.0
            for r in range(b.tensor.shape[0]):
                for z in range(2):
                    for g in range(b.tensor.shape[2]):
                        mass += b.tensor[r, z, g] * likelihood[z, g]
                        if z == 1:
                            active_mass += b.tensor[r, z, g] * likelihood[z, g]
            if mass == 0:
                continue
            posterior_at = category_tensors[category] / mass
            posterior_tau = np.einsum("rab,rag->rbg", steps, posterior_at)
            p_tau = float(posterior_tau[:, 1, :].sum())
            expected_risk += mass * p_tau * (1.0 - p_tau)
            assert 0.0 <= active_mass <= mass
        oracle += p0 * (1.0 - p0) - expected_risk
    oracle *= pv
    actual = _brier(cfg, b, at_h, eval_h, next_h, wind=wind, cloud=cloud)
    assert actual == pytest.approx(oracle, abs=1e-12)
