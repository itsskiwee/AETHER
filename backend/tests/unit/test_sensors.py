"""SCI-01: virtual sensor response functions."""

import math

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from aether.config import load_scenario
from aether.sensors import (
    false_positive_flux_logpdf,
    gsd_effective_m,
    p_detect,
    p_valid,
    pod,
    q50_kg_h,
)


@pytest.fixture(scope="module")
def sensor(base_config_path):
    return load_scenario(base_config_path).model.sensors["vs_a_point_source"]


def test_pod_anchors_at_reference(sensor):
    ref = sensor.pod
    assert gsd_effective_m(sensor, 0.0) == ref.ref_gsd_m
    assert pod(sensor, ref.q50_ref_kg_h, ref.ref_wind_m_s, 0.0) == pytest.approx(0.5, abs=1e-12)
    assert pod(sensor, ref.q90_ref_kg_h, ref.ref_wind_m_s, 0.0) == pytest.approx(0.9, abs=1e-12)


def test_pod_of_zero_flux_is_zero(sensor):
    assert pod(sensor, 0.0, 3.0, 0.0) == 0.0
    assert np.all(pod(sensor, np.array([0.0, 0.0]), 3.0, 10.0) == 0.0)


@given(
    q1=st.floats(0.0, 1e6),
    q2=st.floats(0.0, 1e6),
    wind=st.floats(0.1, 30.0),
    theta=st.floats(0.0, 45.0),
)
def test_pod_monotone_in_flux(sensor, q1, q2, wind, theta):
    lo, hi = sorted((q1, q2))
    assert pod(sensor, lo, wind, theta) <= pod(sensor, hi, wind, theta)


@given(u1=st.floats(1.0, 10.0), u2=st.floats(1.0, 10.0), q=st.floats(1.0, 1e5))
def test_pod_falls_as_wind_rises(sensor, u1, u2, q):
    lo, hi = sorted((u1, u2))
    assert pod(sensor, q, hi, 0.0) <= pod(sensor, q, lo, 0.0)


def test_wind_is_clipped(sensor):
    lo, hi = sensor.pod.wind_clip_m_s
    assert q50_kg_h(sensor, 0.2, 0.0) == q50_kg_h(sensor, lo, 0.0)
    assert q50_kg_h(sensor, 50.0, 0.0) == q50_kg_h(sensor, hi, 0.0)
    assert pod(sensor, 300.0, 6.0, 0.0) < pod(sensor, 300.0, 3.0, 0.0)


def test_off_nadir_coarsens_pixels_and_lowers_pod(sensor):
    assert gsd_effective_m(sensor, 45.0) == pytest.approx(30.0 / math.cos(math.radians(45.0)))
    assert pod(sensor, 150.0, 3.0, 40.0) < pod(sensor, 150.0, 3.0, 0.0)


@given(cloud=st.floats(0.0, 1.0), theta=st.floats(0.0, 40.0))
def test_p_valid_is_a_probability(sensor, cloud, theta):
    assert 0.0 <= p_valid(sensor, cloud, theta, 40.0) <= 1.0


def test_p_valid_edges(sensor):
    assert p_valid(sensor, 1.0, 0.0, 40.0) == 0.0
    assert p_valid(sensor, 0.0, 0.0, 40.0) == pytest.approx(0.95)
    assert p_valid(sensor, 0.0, 40.0, 40.0) == pytest.approx(0.95 * 0.75)
    with pytest.raises(ValueError):
        p_valid(sensor, 0.2, 41.0, 40.0)
    with pytest.raises(ValueError):
        p_valid(sensor, 1.2, 0.0, 40.0)


def test_p_detect_single_definition(sensor):
    assert p_detect(sensor, False, 5000.0, 3.0, 0.0) == sensor.false_positive_prob
    assert p_detect(sensor, True, 150.0, 3.0, 0.0) == pod(sensor, 150.0, 3.0, 0.0)


def test_false_positive_density_normalizes_in_ln_flux(sensor):
    ln_m = np.linspace(-5.0, 15.0, 20001)
    dens = np.exp(false_positive_flux_logpdf(sensor, ln_m))
    assert np.trapezoid(dens, ln_m) == pytest.approx(1.0, abs=1e-9)
    peak = ln_m[np.argmax(dens)]
    assert peak == pytest.approx(math.log(sensor.false_positive_flux.median_kg_h), abs=1e-3)
