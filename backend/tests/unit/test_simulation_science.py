"""Deterministic scientific acceptance checks for truth and synthetic weather."""

from datetime import timedelta

import numpy as np
import pytest
from scipy.special import ndtr
from scipy.stats import kstest

from aether.config import load_scenario
from aether.contracts.models import (
    AcquisitionOption,
    ObservationWindow,
    Source,
    acquisition_option_id,
)
from aether.sensors import p_detect, p_valid
from aether.simulation.outcomes import sample_outcome
from aether.simulation.truth import generate_truth
from aether.weather.synthetic import SyntheticWeather, build_synthetic_weather


def _sources(n: int) -> tuple[Source, ...]:
    return tuple(Source(id=f"src-{i}", lon=-103.0 + i * 0.0001, lat=31.0) for i in range(n))


def test_truncated_lognormal_truth_matches_prior_without_bound_atoms(base_config_path):
    cfg = load_scenario(base_config_path).model.model_copy(update={"horizon_hours": 1})
    sources = _sources(5_000)
    values = np.array(
        [v.median_flux_kg_h for v in generate_truth(cfg, sources, seed=771).sources.values()]
    )
    prior = cfg.sources.flux_prior
    mu, sigma = np.log(prior.median_kg_h), prior.sigma_ln
    cdf_lo = ndtr((np.log(prior.min_kg_h) - mu) / sigma)
    cdf_hi = ndtr((np.log(prior.max_kg_h) - mu) / sigma)

    def truncated_cdf(x):
        return np.clip((ndtr((np.log(x) - mu) / sigma) - cdf_lo) / (cdf_hi - cdf_lo), 0, 1)

    result = kstest(values, truncated_cdf)
    assert result.pvalue > 0.01
    assert np.all(values > prior.min_kg_h)
    assert np.all(values < prior.max_kg_h)
    assert not np.any(values == prior.min_kg_h)
    assert not np.any(values == prior.max_kg_h)


def test_truth_generation_repeats_exactly_and_keeps_source_keying(base_config_path):
    cfg = load_scenario(base_config_path).model.model_copy(update={"horizon_hours": 2})
    sources = _sources(8)
    first = generate_truth(cfg, sources, seed=81)
    second = generate_truth(cfg, sources, seed=81)
    reordered = generate_truth(cfg, tuple(reversed(sources)), seed=81)
    for source in sources:
        a, b = first.sources[source.id], second.sources[source.id]
        assert a.regime == b.regime
        assert a.median_flux_kg_h == b.median_flux_kg_h
        assert np.array_equal(a.active, b.active)
        assert np.array_equal(a.flux_kg_h, b.flux_kg_h)
        c = reordered.sources[source.id]
        assert a.median_flux_kg_h == c.median_flux_kg_h
        assert np.array_equal(a.active, c.active)


def test_regime_frequency_and_initial_activity_match_stationary_model(base_config_path):
    cfg = load_scenario(base_config_path).model.model_copy(update={"horizon_hours": 1})
    n = 10_000
    truth = generate_truth(cfg, _sources(n), seed=991)
    counts = {r.name: 0 for r in cfg.sources.regimes}
    active_counts = {r.name: 0 for r in cfg.sources.regimes}
    for state in truth.sources.values():
        counts[state.regime] += 1
        active_counts[state.regime] += int(state.active[0])
    for regime in cfg.sources.regimes:
        expected_count = n * regime.weight
        assert abs(counts[regime.name] - expected_count) <= 3 * np.sqrt(
            n * regime.weight * (1 - regime.weight)
        )
        expected_active = counts[regime.name] * regime.stationary_p_active
        sd = np.sqrt(expected_active * (1 - regime.stationary_p_active))
        assert abs(active_counts[regime.name] - expected_active) <= 3 * sd


def test_weather_forecast_view_exposes_no_truth_methods(base_config_path):
    cfg = load_scenario(base_config_path).model
    weather = build_synthetic_weather(cfg, _sources(2), model_cfg=cfg, seed=4)
    view = weather.forecast_view()
    assert callable(view.cloud_forecast)
    assert callable(view.wind_forecast)
    assert not hasattr(view, "cloud_truth")
    assert not hasattr(view, "wind_truth")


def test_cloud_mean_and_spatial_correlation_are_configured(base_config_path):
    cfg = load_scenario(base_config_path).model
    # Spatial covariance is evaluated across many pairs at the registered e-folding distance.
    n = 80
    radius_deg = cfg.weather.cloud.spatial_corr_length_km / 111.32
    sources = tuple(
        Source(
            id=f"ring-{i}",
            lon=-103.0 + radius_deg * np.cos(2 * np.pi * i / n),
            lat=31.0 + radius_deg * np.sin(2 * np.pi * i / n),
        )
        for i in range(n)
    )
    long_cfg = cfg.model_copy(update={"horizon_hours": 600.0})
    weather = SyntheticWeather(long_cfg, sources, model_cfg=long_cfg, seed=121)
    cloud = 1.0 / (1.0 + np.exp(-weather._cloud))
    assert float(cloud.mean()) == pytest.approx(cfg.weather.cloud.mean_cloud_fraction, abs=0.02)

    # Correlate pairs at approximately L and check their empirical latent correlation.
    latent = weather._cloud
    pair_i = np.arange(n)
    pair_j = (pair_i + n // 6) % n
    empirical = np.corrcoef(latent[pair_i].ravel(), latent[pair_j].ravel())[0, 1]
    assert empirical == pytest.approx(np.exp(-1.0), abs=0.1)


def test_forecast_error_increases_with_lead_and_events_match_truth_forecast(demo_config_path):
    cfg = load_scenario(demo_config_path).model
    source = _sources(1)
    weather = build_synthetic_weather(cfg, source, model_cfg=cfg, seed=29)
    epoch = cfg.simulation_epoch_utc
    issue = epoch
    leads = (timedelta(hours=1), timedelta(hours=8))
    errors = []
    for lead in leads:
        target = epoch + lead
        fc = weather.cloud_forecast(source[0].id, target, issue)
        tr = weather.cloud_truth(source[0].id, target)
        # Compare in logit space; expected variance grows with configured lead coefficient.
        logit_error = np.log(fc / (1 - fc)) - np.log(tr / (1 - tr))
        errors.append(
            (
                logit_error,
                cfg.weather.forecast.logit_error_sigma_base
                + cfg.weather.forecast.logit_error_sigma_per_lead_hour
                * lead.total_seconds()
                / 3600,
            )
        )
    assert errors[1][1] > errors[0][1]

    # Across keyed realizations, cloud forecast error widens with lead, while wind uses the
    # registered flat PR-W13 uncertainty in PR-B04.
    cloud_error = {1: [], 12: []}
    wind_error = {1: [], 60: []}
    for seed in range(128):
        sample = build_synthetic_weather(cfg, source, model_cfg=cfg, seed=seed)
        for lead_h in cloud_error:
            target = epoch + timedelta(hours=lead_h)
            truth = sample.cloud_truth(source[0].id, target)
            forecast = sample.cloud_forecast(source[0].id, target, issue)
            cloud_error[lead_h].append(
                np.log(forecast / (1 - forecast)) - np.log(truth / (1 - truth))
            )
        for lead_h in wind_error:
            target = epoch + timedelta(hours=lead_h)
            truth = sample.wind_truth(source[0].id, target)
            forecast = sample.wind_forecast(source[0].id, target, issue)
            wind_error[lead_h].append(np.log(forecast / truth))
    assert np.std(cloud_error[12]) > np.std(cloud_error[1])
    for lead_h in wind_error:
        np.testing.assert_allclose(
            np.std(wind_error[lead_h]), cfg.weather.wind.analysis_error_sigma_ln, rtol=0.2
        )

    event_time = epoch + timedelta(hours=21)
    assert weather.cloud_truth(source[0].id, event_time) == 0.9
    injection_time = epoch + timedelta(hours=cfg.weather.injected_events[0].at_hour)
    before = injection_time - timedelta(seconds=1)
    assert weather.latest_issue_time(before) < injection_time
    assert weather.cloud_forecast(source[0].id, event_time, issue) != 0.9
    assert weather.latest_issue_time(injection_time) == injection_time
    assert weather.cloud_forecast(source[0].id, event_time, injection_time) == 0.9


def test_outcome_frequency_matches_sensor_probability_and_is_policy_paired(base_config_path):
    cfg = load_scenario(base_config_path).model.model_copy(update={"horizon_hours": 1})
    n = 100_000
    sources = _sources(n)
    truth = generate_truth(cfg, sources, seed=333)
    sensor = cfg.sensors["vs_a_point_source"]
    spacecraft = cfg.spacecraft["vsat_a"]
    at = cfg.simulation_epoch_utc

    class FixedWeather:
        def cloud_truth(self, source_id, t_utc):
            return 0.0

        def wind_truth(self, source_id, t_utc):
            return 4.0

        def wind_analysis_estimate(self, source_id, t_utc):
            return 4.0

    weather = FixedWeather()
    cloud = 0.0
    theta = 0.0
    pv = p_valid(sensor, cloud, theta, spacecraft.attitude.max_off_nadir_deg)
    expected_detections = 0.0
    observed_detections = 0
    observed_invalid = 0
    for source in sources:
        source_truth = truth.sources[source.id]
        q = source_truth.flux_kg_h[0]
        pd = p_detect(sensor, bool(source_truth.active[0]), float(q), 4.0, theta)
        expected_detections += pv * pd
        wid = f"win-{source.id}"
        option_id = acquisition_option_id(wid, at)
        option = AcquisitionOption(
            option_id=option_id,
            window_id=wid,
            start_utc=at,
            end_utc=at + timedelta(seconds=sensor.exposure_seconds),
            off_nadir_deg=theta,
            sun_elevation_deg=45.0,
            los_unit_ecef=(1.0, 0.0, 0.0),
        )
        window = ObservationWindow(
            id=wid,
            spacecraft_id=spacecraft.id,
            sensor_id=sensor.id,
            source_id=source.id,
            start_utc=at,
            end_utc=at + timedelta(seconds=10),
            pass_id="pass-0",
            orbit_number=0,
            feasible=True,
            min_off_nadir_deg=theta,
            options=(option,),
            duration_s=sensor.exposure_seconds,
            energy_wh=sensor.costs.energy_wh_per_scene,
            data_bytes=sensor.costs.data_bytes_per_scene,
        )
        first = sample_outcome(
            window, at, truth, weather, sensor, 22, option=option, spacecraft_truth=spacecraft
        )
        if source.id == sources[0].id:
            paired = sample_outcome(
                window, at, truth, weather, sensor, 22, option=option, spacecraft_truth=spacecraft
            )
            assert first.model_dump_json() == paired.model_dump_json()
        observed_detections += first.outcome.value == "DETECTION"
        observed_invalid += first.outcome.value == "INVALID_ACQUISITION"

    expected_det = expected_detections / n
    observed_det = observed_detections / n
    sigma_det = np.sqrt(expected_det * (1 - expected_det) / n)
    assert abs(observed_det - expected_det) <= 3 * sigma_det
    expected_invalid = 1.0 - pv
    observed_invalid_fraction = observed_invalid / n
    sigma_invalid = np.sqrt(expected_invalid * pv / n)
    assert abs(observed_invalid_fraction - expected_invalid) <= 3 * sigma_invalid
