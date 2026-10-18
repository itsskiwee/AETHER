from datetime import timedelta

import numpy as np
import pytest
from astropy.time import Time

from aether.config import load_scenario
from aether.contracts.models import Source
from aether.orbit import generate_windows
from aether.planning.checker import _build_satellite, _geometry

ANGULAR_TOLERANCE_DEG = 0.05


@pytest.mark.slow
def test_twenty_l4_options_match_independent_astropy_geometry(repo_root):
    bundle = load_scenario(repo_root / "configs/base.yaml")
    scenario = bundle.model
    sources = [Source(id=f"cross{i}", lon=-103.0 + i * 0.3, lat=32.0 + i * 0.2) for i in range(3)]
    windows = generate_windows(
        scenario,
        sources,
        scenario.simulation_epoch_utc,
        scenario.simulation_epoch_utc + timedelta(hours=72),
    )
    options = [
        (window, option) for window in windows if window.feasible for option in window.options
    ]
    assert len(options) >= 20
    samples = [options[round(i * (len(options) - 1) / 19)] for i in range(20)]

    off_nadir_diffs = []
    sun_elevation_diffs = []
    for window, option in samples:
        source = next(item for item in sources if item.id == window.source_id)
        satellite = _build_satellite(scenario.spacecraft[window.spacecraft_id])
        off_nadir, _horizon, sun_elevation, _los = _geometry(
            satellite, source, Time(option.start_utc, scale="utc")
        )
        off_nadir_diffs.append(abs(off_nadir - option.off_nadir_deg))
        sun_elevation_diffs.append(abs(sun_elevation - option.sun_elevation_deg))

    assert len(off_nadir_diffs) == len(sun_elevation_diffs) == 20
    assert np.max(off_nadir_diffs) <= ANGULAR_TOLERANCE_DEG
    assert np.max(sun_elevation_diffs) <= ANGULAR_TOLERANCE_DEG
