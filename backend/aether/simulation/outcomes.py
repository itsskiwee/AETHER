"""Seeded observation-outcome sampling with truth kept behind the simulator boundary."""

from __future__ import annotations

import math
from datetime import datetime

from aether.config import SensorProfile, SpacecraftProfile
from aether.contracts.enums import ObservationOutcome
from aether.contracts.models import (
    AcquisitionOption,
    ObservationWindow,
    SimulatedAcquisition,
    acquisition_option_id,
)
from aether.rng import keyed_rng, minute_bucket, stream_key
from aether.simulation.truth_types import TruthHistory
from aether.weather.synthetic import SyntheticWeather


def sample_outcome(
    window: ObservationWindow,
    start_utc: datetime,
    truth: TruthHistory,
    weather: SyntheticWeather,
    sensor_truth: SensorProfile,
    seed: int,
    *,
    option: AcquisitionOption | None = None,
    spacecraft_truth: SpacecraftProfile,
) -> SimulatedAcquisition:
    """Sample one acquisition using source truth and truth-side weather.

    The returned contract contains only the observation, an analysis-style wind estimate and
    scene-observed cloud. It never contains latent source state or true wind.
    """
    # L2 owns these shared likelihood helpers; import at call time so this module remains
    # importable while that lane is implementing its interface.
    from aether.sensors import p_detect, p_valid

    if start_utc.tzinfo is None or start_utc.utcoffset() is None:
        raise ValueError("start_utc must be timezone-aware")
    if option is not None:
        if option.window_id != window.id or option.start_utc != start_utc:
            raise ValueError("option must belong to the window and match start_utc")
        option_id = option.option_id
        off_nadir_deg = option.off_nadir_deg
    else:
        option_id = acquisition_option_id(window.id, start_utc)
        off_nadir_deg = window.min_off_nadir_deg

    source = truth.sources[window.source_id]
    hour = truth.hour_index(start_utc)
    is_active = bool(source.active[hour])
    q_kg_h = float(source.flux_kg_h[hour])
    wind_true_m_s = weather.wind_truth(window.source_id, start_utc)
    cloud_fraction = weather.cloud_truth(window.source_id, start_utc)
    rng = keyed_rng(
        seed,
        "outcome",
        window.source_id,
        window.spacecraft_id,
        window.sensor_id,
        minute_bucket(start_utc),
    )
    u_valid, u_detect, z_flux, u_fp_flux = rng.random(4)
    p_scene_valid = p_valid(
        sensor_truth,
        cloud_fraction,
        off_nadir_deg,
        spacecraft_truth.attitude.max_off_nadir_deg,
    )

    if u_valid >= p_scene_valid:
        outcome = ObservationOutcome.INVALID_ACQUISITION
        measured_flux = None
    else:
        p_detection = p_detect(sensor_truth, is_active, q_kg_h, wind_true_m_s, off_nadir_deg)
        if u_detect < p_detection:
            outcome = ObservationOutcome.DETECTION
            if is_active:
                measured_flux = q_kg_h * math.exp(
                    sensor_truth.flux_measurement.sigma_ln * _standard_normal(z_flux)
                )
            else:
                fp = sensor_truth.false_positive_flux
                measured_flux = fp.median_kg_h * math.exp(fp.sigma_ln * _standard_normal(u_fp_flux))
        else:
            outcome = ObservationOutcome.VALID_NON_DETECTION
            measured_flux = None

    return SimulatedAcquisition(
        id=f"acq:{option_id}",
        option_id=option_id,
        window_id=window.id,
        source_id=window.source_id,
        spacecraft_id=window.spacecraft_id,
        sensor_id=window.sensor_id,
        time_utc=start_utc,
        outcome=outcome,
        measured_flux_kg_h=measured_flux,
        off_nadir_deg=off_nadir_deg,
        wind_estimate_m_s=weather.wind_analysis_estimate(window.source_id, start_utc),
        scene_cloud_fraction=cloud_fraction,
        rng_key=stream_key(
            seed,
            "outcome",
            window.source_id,
            window.spacecraft_id,
            window.sensor_id,
            minute_bucket(start_utc),
        ),
    )


def _standard_normal(uniform: float) -> float:
    """Transform a U(0,1) draw to N(0,1) without consuming another keyed draw."""
    from scipy.special import ndtri

    return float(ndtri(min(max(uniform, 1e-15), 1.0 - 1e-15)))


