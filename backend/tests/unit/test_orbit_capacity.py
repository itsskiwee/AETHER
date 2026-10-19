from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location

import numpy as np

from aether.config import load_scenario
from aether.contracts.models import AcquisitionOption, ObservationWindow, acquisition_option_id


def _load_builder(repo_root):
    path = repo_root / "scripts" / "build_orbit_candidate.py"
    spec = spec_from_file_location("build_orbit_candidate", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _window(window_id, start_seconds, los):
    start = datetime(2026, 10, 17, tzinfo=UTC) + timedelta(seconds=start_seconds)
    end = start + timedelta(seconds=3)
    option = AcquisitionOption(
        option_id=acquisition_option_id(window_id, start),
        window_id=window_id,
        start_utc=start,
        end_utc=end,
        off_nadir_deg=5.0,
        sun_elevation_deg=40.0,
        los_unit_ecef=tuple(float(value) for value in los),
    )
    return ObservationWindow(
        id=window_id,
        spacecraft_id="vsat_a",
        sensor_id="vs_a_point_source",
        source_id=f"source-{window_id}",
        start_utc=start,
        end_utc=end,
        pass_id="vsat_a:1",
        orbit_number=1,
        feasible=True,
        rejection_reasons=(),
        min_off_nadir_deg=5.0,
        options=(option,),
        duration_s=3.0,
        energy_wh=0.1,
        data_bytes=1,
    )


def test_pass_capacity_uses_slew_and_maximizes_feasible_schedule_count(repo_root):
    cfg = load_scenario(repo_root / "configs" / "base.yaml").model
    builder = _load_builder(repo_root)
    thirty_degrees = np.deg2rad(30.0)
    windows = [
        _window("first", 0, (1.0, 0.0, 0.0)),
        _window("too-soon", 8, (np.cos(thirty_degrees), np.sin(thirty_degrees), 0.0)),
        _window("later", 40, (np.cos(thirty_degrees), np.sin(thirty_degrees), 0.0)),
    ]

    capacity = builder._schedule_pass_capacity(windows, cfg.spacecraft["vsat_a"], cfg)

    assert capacity["solver_status"] == "OPTIMAL"
    assert capacity["scheduled_acquisitions"] == 2
    assert len(capacity["selected_option_ids"]) == 2
