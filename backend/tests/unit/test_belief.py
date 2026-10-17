"""SCI-03..SCI-05, SCI-07: belief filter invariants and closed-form fixtures."""

import math
from datetime import timedelta

import numpy as np
import pytest

from aether.belief import SourceBelief
from aether.config import load_scenario
from aether.contracts.enums import ObservationOutcome as O
from aether.contracts.enums import Regime
from aether.contracts.models import SimulatedAcquisition
from aether.sensors import pod

SENSOR_ID = "vs_a_point_source"


@pytest.fixture(scope="module")
def cfg(base_config_path):
    return load_scenario(base_config_path).model


def _acq(cfg, outcome, *, hours=18.0, flux=None, wind=4.0, theta=10.0, source="s0", tag=""):
    t = cfg.simulation_epoch_utc + timedelta(hours=hours)
    return SimulatedAcquisition(
        id=f"acq-{source}-{hours}-{outcome}-{tag}",
        option_id="w#0",
        window_id="w",
        source_id=source,
        spacecraft_id="vsat_a",
        sensor_id=SENSOR_ID,
        time_utc=t,
        outcome=outcome,
        measured_flux_kg_h=flux,
        off_nadir_deg=theta,
        wind_estimate_m_s=wind,
        scene_cloud_fraction=0.1,
        rng_key="test",
    )


def _replace(model, **fields):
    return model.model_copy(update=fields)


def _simple_cfg(cfg):
    """One regime, no hourly variability, no wind error: POD is exact at each grid point."""
    regime = _replace(cfg.sources.regimes[1], weight=1.0)
    sources = _replace(cfg.sources, regimes=(regime,), hourly_variability_sigma_ln=0.0)
    wind = _replace(cfg.weather.wind, analysis_error_sigma_ln=0.0)
    weather = _replace(cfg.weather, wind=wind)
    return _replace(cfg, sources=sources, weather=weather)


# --- SCI-03 prior and predict ---------------------------------------------------------------


def test_prior_normalized_and_matches_regime_mixture(cfg):
    b = SourceBelief.prior("s0", cfg)
    assert b.tensor.shape == (3, 2, cfg.planner.belief_grid.flux_points)
    assert abs(b.tensor.sum() - 1.0) < 1e-12
    expected = sum(r.weight * r.stationary_p_active for r in cfg.sources.regimes)
    assert b.p_active() == pytest.approx(expected, abs=1e-12)
    assert b.regime_probs()[Regime.PERSISTENT] == pytest.approx(0.15, abs=1e-12)
    assert not b.tensor.flags.writeable


def test_prior_respects_flux_truncation(cfg):
    b = SourceBelief.prior("s0", cfg)
    q = np.exp(b.model.ln_edges)
    outside = (q[1:] <= cfg.sources.flux_prior.min_kg_h) | (
        q[:-1] >= cfg.sources.flux_prior.max_kg_h
    )
    assert np.all(b.flux_mass()[outside] == 0.0)
    assert b.flux_median_kg_h() == pytest.approx(cfg.sources.flux_prior.median_kg_h, rel=0.05)


def test_predict_without_evidence_keeps_stationary_prior(cfg):
    b = SourceBelief.prior("s0", cfg)
    later = b.predict(cfg.simulation_epoch_utc + timedelta(hours=37))
    assert later.p_active() == pytest.approx(b.p_active(), abs=1e-12)
    assert abs(later.tensor.sum() - 1.0) < 1e-12
    assert later.received_new_evidence is False
    assert later.snapshot().received_new_evidence is False


def test_predict_converges_to_posterior_regime_mixture(cfg):
    b = SourceBelief.prior("s0", cfg).update(
        _acq(cfg, O.DETECTION, flux=500.0), sensor=_sensor(cfg)
    )
    far = b.predict(cfg.simulation_epoch_utc + timedelta(hours=18 + 2000))
    stationary = {r.name: r.stationary_p_active for r in cfg.sources.regimes}
    expected = sum(p * stationary[r] for r, p in b.regime_probs().items())
    assert far.p_active() == pytest.approx(expected, abs=1e-9)
    assert far.regime_probs() == pytest.approx(b.regime_probs(), abs=1e-12)
    assert far.received_new_evidence is False
    assert far.evidence_ids == b.evidence_ids


def test_predict_backwards_is_rejected(cfg):
    b = SourceBelief.prior("s0", cfg).predict(cfg.simulation_epoch_utc + timedelta(hours=5))
    with pytest.raises(ValueError):
        b.predict(cfg.simulation_epoch_utc + timedelta(hours=4))


def _sensor(cfg):
    return cfg.sensors[SENSOR_ID]


# --- SCI-04 updates -------------------------------------------------------------------------


@pytest.mark.parametrize("outcome", [O.INVALID_ACQUISITION, O.NOT_OBSERVED])
def test_missing_evidence_leaves_tensor_bit_identical(cfg, outcome):
    b = SourceBelief.prior("s0", cfg).predict(cfg.simulation_epoch_utc + timedelta(hours=3))
    after = b.update(_acq(cfg, outcome), sensor=_sensor(cfg))
    assert after is b
    assert np.array_equal(after.tensor, b.tensor)
    assert after.evidence_ids == ()


def test_invalid_is_not_a_non_detection(cfg):
    b = SourceBelief.prior("s0", cfg)
    nd = b.update(_acq(cfg, O.VALID_NON_DETECTION), sensor=_sensor(cfg))
    inv = b.update(_acq(cfg, O.INVALID_ACQUISITION), sensor=_sensor(cfg))
    assert nd.p_active() < inv.p_active() - 0.05


def test_high_pod_non_detection_is_more_informative(cfg):
    b = SourceBelief.prior("s0", cfg)
    s = _sensor(cfg)
    high = b.update(_acq(cfg, O.VALID_NON_DETECTION, wind=1.5, theta=0.0), sensor=s)
    low = b.update(_acq(cfg, O.VALID_NON_DETECTION, wind=10.0, theta=40.0), sensor=s)
    prior = b.predict(high.state_time_utc).p_active()
    assert high.p_active() < low.p_active() < prior


def test_non_detection_matches_hand_computed_fixture(cfg):
    c = _simple_cfg(cfg)
    s = _sensor(c)
    b = SourceBelief.prior("s0", c)
    t = 18.0
    prior = b.predict(c.simulation_epoch_utc + timedelta(hours=t))
    p = prior.p_active()
    w = prior.tensor[0, 1, :] / prior.tensor[0, 1, :].sum()
    q = np.exp(b.model.ln_q)
    pd = float(w @ pod(s, q, 4.0, 10.0))
    fp = s.false_positive_prob
    expected = p * (1 - pd) / (p * (1 - pd) + (1 - p) * (1 - fp))
    post = b.update(_acq(c, O.VALID_NON_DETECTION, hours=t), sensor=s)
    assert post.p_active() == pytest.approx(expected, abs=1e-12)


def test_detection_matches_hand_computed_fixture(cfg):
    c = _simple_cfg(cfg)
    s = _sensor(c)
    b = SourceBelief.prior("s0", c)
    t, m = 18.0, 250.0
    prior = b.predict(c.simulation_epoch_utc + timedelta(hours=t))
    p = prior.p_active()
    w = prior.tensor[0, 1, :] / prior.tensor[0, 1, :].sum()
    q = np.exp(b.model.ln_q)
    sm = s.flux_measurement.sigma_ln
    dens = np.exp(-0.5 * ((math.log(m) - np.log(q)) / sm) ** 2) / (sm * math.sqrt(2 * math.pi))
    act = p * float(w @ (pod(s, q, 4.0, 10.0) * dens))
    fpd = s.false_positive_flux
    zf = (math.log(m) - math.log(fpd.median_kg_h)) / fpd.sigma_ln
    ina = (
        (1 - p)
        * s.false_positive_prob
        * math.exp(-0.5 * zf * zf)
        / (fpd.sigma_ln * math.sqrt(2 * math.pi))
    )
    post = b.update(_acq(c, O.DETECTION, hours=t, flux=m), sensor=s)
    assert post.p_active() == pytest.approx(act / (act + ina), abs=1e-12)


def test_posterior_does_not_depend_on_flux_units(cfg):
    """Rescale every flux quantity (kg/h -> kg/s): p_active must not change (PR-V21)."""
    k = 1.0 / 3600.0
    fpr = cfg.sources.flux_prior
    sources = _replace(
        cfg.sources,
        flux_prior=_replace(
            fpr,
            median_kg_h=fpr.median_kg_h * k,
            min_kg_h=fpr.min_kg_h * k,
            max_kg_h=fpr.max_kg_h * k,
        ),
    )
    grid = cfg.planner.belief_grid
    planner = _replace(
        cfg.planner,
        belief_grid=_replace(
            grid, flux_min_kg_h=grid.flux_min_kg_h * k, flux_max_kg_h=grid.flux_max_kg_h * k
        ),
    )
    s = _sensor(cfg)
    s_scaled = _replace(
        s,
        pod=_replace(
            s.pod, q50_ref_kg_h=s.pod.q50_ref_kg_h * k, q90_ref_kg_h=s.pod.q90_ref_kg_h * k
        ),
        false_positive_flux=_replace(
            s.false_positive_flux, median_kg_h=s.false_positive_flux.median_kg_h * k
        ),
    )
    scaled = _replace(cfg, sources=sources, planner=planner, sensors={SENSOR_ID: s_scaled})
    for m in (60.0, 150.0, 900.0):
        a = SourceBelief.prior("s0", cfg).update(_acq(cfg, O.DETECTION, flux=m), sensor=s)
        b = SourceBelief.prior("s0", scaled).update(
            _acq(scaled, O.DETECTION, flux=m * k), sensor=s_scaled
        )
        assert b.p_active() == pytest.approx(a.p_active(), abs=1e-10)
        assert b.flux_median_kg_h() == pytest.approx(a.flux_median_kg_h() * k, rel=1e-9)


def test_update_rejects_wrong_source_or_sensor(cfg):
    b = SourceBelief.prior("s0", cfg)
    with pytest.raises(ValueError):
        b.update(_acq(cfg, O.VALID_NON_DETECTION, source="s1"), sensor=_sensor(cfg))
    other = _replace(_sensor(cfg), id="other")
    with pytest.raises(ValueError):
        b.update(_acq(cfg, O.VALID_NON_DETECTION), sensor=other)


# --- SCI-05 flux ----------------------------------------------------------------------------


def test_detection_moves_flux_toward_measurement_and_narrows(cfg):
    b = SourceBelief.prior("s0", cfg)
    lo0, hi0 = b.flux_ci90_kg_h()
    post = b.update(_acq(cfg, O.DETECTION, flux=2000.0), sensor=_sensor(cfg))
    lo1, hi1 = post.flux_ci90_kg_h()
    assert b.flux_median_kg_h() < post.flux_median_kg_h() < 2000.0
    assert math.log(hi1 / lo1) < math.log(hi0 / lo0)
    snap = post.snapshot()
    assert snap.flux_ci90_kg_h[0] <= snap.flux_median_kg_h <= snap.flux_ci90_kg_h[1]
    assert snap.received_new_evidence is True
    assert snap.evidence_ids == (post.evidence_ids[0],)


# --- SCI-07 regime learning -----------------------------------------------------------------


def test_repeated_detections_raise_persistent_regime(cfg):
    b = SourceBelief.prior("s0", cfg)
    prior = b.regime_probs()[Regime.PERSISTENT]
    for i, h in enumerate((18.0, 28.0, 38.0)):
        b = b.update(_acq(cfg, O.DETECTION, hours=h, flux=400.0, tag=str(i)), sensor=_sensor(cfg))
    assert b.regime_probs()[Regime.PERSISTENT] > prior
    assert b.regime_probs()[Regime.EPISODIC] < 0.01
    assert len(b.evidence_ids) == 3


# --- m0 calibration (G3 condition): the filter is Bayes-consistent with its own model ---------


def test_one_observation_calibration_under_the_model(cfg):
    """Simulate sources from the model's generative process (regime, Q, z, hourly eps, wind error)
    and check calibration of the posterior p_active after one observation at T+18 h."""
    s = _sensor(cfg)
    rng = np.random.default_rng(20261017)
    regimes = cfg.sources.regimes
    fpr = cfg.sources.flux_prior
    prior = SourceBelief.prior("s0", cfg)
    n, h = 3000, 18
    p_post, z_true = np.empty(n), np.empty(n)
    for i in range(n):
        r = regimes[rng.choice(len(regimes), p=[x.weight for x in regimes])]
        while True:
            q_med = math.exp(rng.normal(math.log(fpr.median_kg_h), fpr.sigma_ln))
            if fpr.min_kg_h <= q_med <= fpr.max_kg_h:
                break
        z = rng.random() < r.stationary_p_active
        for _ in range(h):
            z = (rng.random() >= r.p_on_to_off) if z else (rng.random() < r.p_off_to_on)
        wind_true = 4.0
        wind_est = wind_true * math.exp(cfg.weather.wind.analysis_error_sigma_ln * rng.normal())
        q = q_med * math.exp(rng.normal(0.0, cfg.sources.hourly_variability_sigma_ln))
        if z:
            det = rng.random() < pod(s, q, wind_true, 10.0)
            flux = q * math.exp(s.flux_measurement.sigma_ln * rng.normal()) if det else None
        else:
            det = rng.random() < s.false_positive_prob
            fp = s.false_positive_flux
            flux = fp.median_kg_h * math.exp(fp.sigma_ln * rng.normal()) if det else None
        acq = _acq(
            cfg, O.DETECTION if det else O.VALID_NON_DETECTION, hours=h, flux=flux, wind=wind_est
        )
        p_post[i] = prior.update(acq, sensor=s).p_active()
        z_true[i] = z
    # Calibration in the large, and per reliability bin, within 3 standard errors.
    se = math.sqrt(np.mean(p_post * (1 - p_post)) / n)
    assert abs(p_post.mean() - z_true.mean()) < 3 * se + 1e-3
    for lo, hi in ((0.0, 0.2), (0.2, 0.8), (0.8, 1.0)):
        sel = (p_post >= lo) & (p_post < hi)
        if sel.sum() < 50:
            continue
        se_bin = math.sqrt(max(np.mean(p_post[sel] * (1 - p_post[sel])), 1e-4) / sel.sum())
        assert abs(p_post[sel].mean() - z_true[sel].mean()) < 3 * se_bin + 0.01
