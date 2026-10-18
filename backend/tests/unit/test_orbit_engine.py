from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from pyproj import Geod
from skyfield.api import wgs84

from aether.config import load_scenario
from aether.contracts.models import AcquisitionOption, Source, acquisition_option_id
from aether.orbit import (
    _check_sgp4,
    _ltdn_error_seconds,
    _scalar_geometry,
    _timescale,
    build_satellite,
    generate_windows,
    load_ephemeris,
    slew_time_s,
)
from aether.orbit import ephemeris as ephemeris_fetcher


@pytest.fixture(scope="module")
def cfg(base_config_path):
    return load_scenario(base_config_path).model


def _sun_elevation(value):
    def provide(_source, times):
        shape = np.shape(times.whole)
        return np.full(shape, value, dtype=float) if shape else float(value)

    return provide


def _overhead(cfg, spacecraft_id="vsat_a"):
    profile = cfg.spacecraft[spacecraft_id]
    satellite = build_satellite(profile)
    when = cfg.simulation_epoch_utc + timedelta(hours=1)
    position = satellite.at(_timescale().from_datetime(when))
    location = wgs84.geographic_position_of(position)
    source = Source(
        id="overhead",
        lon=location.longitude.degrees,
        lat=location.latitude.degrees,
    )
    return profile, satellite, when, source


def _spacecraft_windows(cfg, source, when, *, spacecraft_id="vsat_a", half_span_s=180, sun=45):
    return [
        window
        for window in generate_windows(
            cfg,
            [source],
            when - timedelta(seconds=half_span_s),
            when + timedelta(seconds=half_span_s),
            sun_elevation_fn=_sun_elevation(sun),
        )
        if window.spacecraft_id == spacecraft_id and window.source_id == source.id
    ]


def test_build_satellite_altitude_period_and_sgp4_error(cfg):
    satellite = build_satellite(cfg.spacecraft["vsat_a"])
    epoch = _timescale().from_datetime(cfg.simulation_epoch_utc)
    altitude_km = np.linalg.norm(satellite.at(epoch).position.km) - 6378.135
    period_min = 2.0 * np.pi / satellite.model.no_kozai

    assert altitude_km == pytest.approx(500.0, abs=5.0)
    assert period_min == pytest.approx(94.62, abs=0.05)

    broken = SimpleNamespace(model=SimpleNamespace(sgp4=lambda *_: (6, (0, 0, 0), (0, 0, 0))))
    with pytest.raises(RuntimeError, match="error code 6"):
        _check_sgp4(broken, SimpleNamespace(whole=1.0, ut1_fraction=0.5))


def test_pinned_ephemeris_and_shared_eop_are_loaded_offline(cfg):
    timescale = _timescale()
    assert timescale.from_datetime(cfg.simulation_epoch_utc).tt > 0
    assert "SUN" in str(load_ephemeris()["sun"])


def test_ephemeris_fetcher_reuses_verified_pin_without_network(monkeypatch):
    monkeypatch.setattr(
        ephemeris_fetcher,
        "assert_public_address",
        lambda *_: pytest.fail("verified local pin should not trigger DNS"),
    )
    assert ephemeris_fetcher.fetch_ephemeris() == ephemeris_fetcher.TARGET


def test_configured_ltdn_matches_pinned_solar_ephemeris(cfg):
    ephemeris = load_ephemeris()
    for profile in cfg.spacecraft.values():
        assert _ltdn_error_seconds(profile, ephemeris) <= 120.0


def test_overhead_offtrack_and_night_windows_are_classified(cfg):
    _, _, when, source = _overhead(cfg)
    overhead = _spacecraft_windows(cfg, source, when)
    usable = [window for window in overhead if window.feasible]
    assert usable
    assert min(window.min_off_nadir_deg for window in usable) < 1.0

    geod = Geod(ellps="WGS84")
    lon, lat, _ = geod.fwd(source.lon, source.lat, 90.0, 2_000_000.0)
    offtrack = Source(id="offtrack", lon=lon, lat=lat)
    rejected = _spacecraft_windows(cfg, offtrack, when, half_span_s=30)
    assert rejected
    assert any(
        {"POINTING", "NOT_VISIBLE"}.intersection(reason.value for reason in w.rejection_reasons)
        for w in rejected
    )

    dark = _spacecraft_windows(cfg, source, when, sun=-10.0)
    assert any(not w.feasible and "DARK" in {r.value for r in w.rejection_reasons} for w in dark)


def test_short_edge_window_is_found_and_options_use_their_own_times(cfg):
    profile, satellite, when, source = _overhead(cfg)
    narrow_profile = profile.model_copy(
        update={"attitude": profile.attitude.model_copy(update={"max_off_nadir_deg": 5.0})}
    )
    narrow_cfg = cfg.model_copy(
        update={"spacecraft": {**cfg.spacecraft, profile.id: narrow_profile}}
    )
    windows = _spacecraft_windows(narrow_cfg, source, when, half_span_s=100, sun=45.0)
    short = next(
        window
        for window in windows
        if window.feasible and 8.0 <= (window.end_utc - window.start_utc).total_seconds() <= 20.0
    )
    assert (short.end_utc - short.start_utc).total_seconds() == pytest.approx(12.0, abs=1.0)
    assert len(short.options) >= 2

    tolerance_s = narrow_cfg.window_search.refine_tolerance_s
    start_before = _scalar_geometry(
        satellite,
        source,
        short.start_utc - timedelta(seconds=tolerance_s),
        None,
        None,
        _sun_elevation(45.0),
    )[0]
    start_after = _scalar_geometry(
        satellite,
        source,
        short.start_utc + timedelta(seconds=tolerance_s),
        None,
        None,
        _sun_elevation(45.0),
    )[0]
    end_before = _scalar_geometry(
        satellite,
        source,
        short.end_utc - timedelta(seconds=tolerance_s),
        None,
        None,
        _sun_elevation(45.0),
    )[0]
    end_after = _scalar_geometry(
        satellite,
        source,
        short.end_utc + timedelta(seconds=tolerance_s),
        None,
        None,
        _sun_elevation(45.0),
    )[0]
    limit_deg = narrow_profile.attitude.max_off_nadir_deg
    assert start_before > limit_deg and start_after <= limit_deg
    assert end_before <= limit_deg and end_after > limit_deg

    option_los = []
    for option in short.options:
        off, _, _, los = _scalar_geometry(
            satellite,
            source,
            option.start_utc,
            None,
            None,
            _sun_elevation(45.0),
        )
        assert option.off_nadir_deg == pytest.approx(off, abs=1e-8)
        assert option.los_unit_ecef == pytest.approx(los, abs=1e-8)
        option_los.append(option.los_unit_ecef)
    assert len(set(option_los)) > 1


@pytest.mark.parametrize("limit_deg", [5.0, 40.0])
def test_refined_options_stay_inside_physical_limits_for_entire_exposure(cfg, limit_deg):
    """Regression: midpoint refinement emitted a real 40.011033-degree option."""
    profile, satellite, when, source = _overhead(cfg)
    profile = profile.model_copy(
        update={"attitude": profile.attitude.model_copy(update={"max_off_nadir_deg": limit_deg})}
    )
    cfg = cfg.model_copy(update={"spacecraft": {profile.id: profile}})
    windows = _spacecraft_windows(cfg, source, when)
    options = [option for window in windows for option in window.options]
    assert options
    for option in options:
        assert option.off_nadir_deg <= limit_deg
        for instant in (option.start_utc, option.end_utc):
            off, elevation, sun, _ = _scalar_geometry(
                satellite, source, instant, None, None, _sun_elevation(45.0)
            )
            assert off <= limit_deg
            assert elevation > 0
            assert sun >= cfg.sensors[windows[0].sensor_id].min_sun_elevation_deg


def _option(window_id, at, los):
    return AcquisitionOption(
        option_id=acquisition_option_id(window_id, at),
        window_id=window_id,
        start_utc=at,
        end_utc=at + timedelta(seconds=3),
        off_nadir_deg=0.0,
        sun_elevation_deg=45.0,
        los_unit_ecef=los,
    )


def test_slew_time_includes_settle_and_angular_motion(cfg):
    at = datetime(2026, 10, 17, tzinfo=UTC)
    attitude = cfg.spacecraft["vsat_a"].attitude
    same = _option("same", at, (1.0, 0.0, 0.0))
    same_next = _option("same-next", at + timedelta(seconds=1), (1.0, 0.0, 0.0))
    thirty_deg = _option("thirty", at + timedelta(seconds=2), (np.cos(np.deg2rad(30)), 0.5, 0.0))

    assert slew_time_s(same, same_next, attitude) == pytest.approx(attitude.settle_seconds)
    assert slew_time_s(same, thirty_deg, attitude) == pytest.approx(
        30.0 / attitude.slew_rate_deg_s + attitude.settle_seconds
    )


def test_generated_slew_uses_real_exposure_end_geometry(cfg):
    profile, satellite, when, source = _overhead(cfg)
    options = sorted(
        (option for window in _spacecraft_windows(cfg, source, when) for option in window.options),
        key=lambda option: option.start_utc,
    )
    assert len(options) >= 2
    previous, following = options[0], options[-1]
    previous_end = _scalar_geometry(
        satellite, source, previous.end_utc, None, None, _sun_elevation(45.0)
    )[3]
    next_start = _scalar_geometry(
        satellite, source, following.start_utc, None, None, _sun_elevation(45.0)
    )[3]
    assert previous.end_los_unit_ecef == pytest.approx(previous_end, abs=1e-12)
    assert not np.allclose(previous.los_unit_ecef, previous_end, atol=1e-5)
    angle_deg = np.degrees(np.arccos(np.clip(np.dot(previous_end, next_start), -1.0, 1.0)))
    expected_s = angle_deg / profile.attitude.slew_rate_deg_s + profile.attitude.settle_seconds
    assert slew_time_s(previous, following, profile.attitude) == pytest.approx(expected_s)
    legacy_angle_deg = np.degrees(
        np.arccos(np.clip(np.dot(previous.los_unit_ecef, next_start), -1.0, 1.0))
    )
    legacy_s = legacy_angle_deg / profile.attitude.slew_rate_deg_s + profile.attitude.settle_seconds
    assert abs(expected_s - legacy_s) > 0.1
    for option in options:
        end_los = _scalar_geometry(
            satellite, source, option.end_utc, None, None, _sun_elevation(45.0)
        )[3]
        assert option.end_los_unit_ecef == pytest.approx(end_los, abs=1e-12)


def test_pinned_timescale_includes_polar_motion():
    timescale = _timescale()
    assert timescale.polar_motion_table is not None
    tt, x_arcseconds, y_arcseconds = timescale.polar_motion_table
    assert len(tt) == len(x_arcseconds) == len(y_arcseconds) > 0
    assert np.all(np.isfinite(tt))
    assert np.all(np.isfinite(x_arcseconds))
    assert np.all(np.isfinite(y_arcseconds))
    assert np.any(x_arcseconds != 0.0)
    assert np.any(y_arcseconds != 0.0)
