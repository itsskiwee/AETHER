"""EVL-08: oracle reference policy values and capacity/demand diagnostics."""

from datetime import timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from aether.config import load_scenario
from aether.contracts import (
    AcquisitionOption,
    CandidateUtility,
    ObservationWindow,
    PolicyId,
    Regime,
    RunRecord,
    Source,
)
from aether.evaluation.reference import OraclePolicy, capacity_report, gate_report
from aether.simulation.truth_types import SourceTruth, TruthHistory


@pytest.fixture(scope="module")
def cfg(base_config_path):
    return load_scenario(base_config_path).model


def _window(wid, source, start, pass_id="p1", sat="vsat_a"):
    opt = AcquisitionOption(
        id=f"{wid}#0",
        window_id=wid,
        index=0,
        start_utc=start,
        end_utc=start + timedelta(seconds=3),
        off_nadir_deg=5.0,
        sun_elevation_deg=40.0,
        los_unit_ecef=(0.0, 0.0, -1.0),
    )
    return ObservationWindow(
        id=wid, spacecraft_id=sat, sensor_id="vs_a_point_source", source_id=source,
        start_utc=start, end_utc=start + timedelta(seconds=30), pass_id=pass_id, orbit_number=1,
        feasible=True, min_off_nadir_deg=5.0, options=(opt,), duration_s=3.0, energy_wh=0.2,
        data_bytes=306_000_000,
    )  # fmt: skip


def _utility(wid, p_valid):
    return CandidateUtility(
        window_id=wid, plan_revision=0, expected_info_gain_bits=0.5, decision_relevance=0.0,
        latency_s=0.0, resource_cost=0.0, p_valid_forecast=p_valid, utility=0.5,
        integer_utility=5000,
    )  # fmt: skip


@pytest.fixture(scope="module")
def truth(cfg):
    hours = int(cfg.horizon_hours)
    on, off = np.ones(hours, bool), np.zeros(hours, bool)
    return TruthHistory(
        epoch_utc=cfg.simulation_epoch_utc, hours=hours,
        sources={
            "A": SourceTruth(source_id="A", regime=Regime.PERSISTENT, median_flux_kg_h=300.0,
                             active=on, flux_kg_h=np.full(hours, 300.0)),
            "B": SourceTruth(source_id="B", regime=Regime.EPISODIC, median_flux_kg_h=100.0,
                             active=off, flux_kg_h=np.zeros(hours)),
        },
    )  # fmt: skip


def _ctx(cfg, windows, utilities, p_now):
    return SimpleNamespace(
        run_id="r", revision=0, now_utc=cfg.simulation_epoch_utc, cause="test", cfg=cfg,
        windows=tuple(windows), committed=(), utilities=utilities,
        posterior_mean_flux_kg_h={}, p_active_by_source=p_now,
    )  # fmt: skip


def test_oracle_values_are_removable_squared_error(cfg, truth):
    t = cfg.simulation_epoch_utc + timedelta(hours=20)
    wa, wb = _window("wa", "A", t), _window("wb", "B", t)
    ctx = _ctx(cfg, [wa, wb], {"wa": _utility("wa", 0.8), "wb": _utility("wb", 0.5)},
               {"A": 0.9, "B": 0.9})  # fmt: skip
    values = OraclePolicy(truth).window_values(ctx)
    # A is active: (0.9 - 1)^2 * 0.8 = 0.008. B is inactive: (0.9 - 0)^2 * 0.5 = 0.405
    assert values == {"wa": pytest.approx(0.008), "wb": pytest.approx(0.405)}


def test_oracle_picks_the_most_wrong_belief_when_windows_conflict(cfg, truth):
    t = cfg.simulation_epoch_utc + timedelta(hours=20)
    wa, wb = _window("wa", "A", t), _window("wb", "B", t)  # same satellite, same time
    ctx = _ctx(cfg, [wa, wb], {"wa": _utility("wa", 0.8), "wb": _utility("wb", 0.5)},
               {"A": 0.9, "B": 0.9})  # fmt: skip
    plan = OraclePolicy(truth).plan(ctx)
    assert plan.policy_id is PolicyId.ORACLE
    assert plan.selected_option_ids == ("wb#0",)


def _run(windows, sources=("A", "B"), acquisitions=()):
    return RunRecord(
        run_id="r", policy_id=PolicyId.RANDOM_FEASIBLE, scenario_id="s", family="m0_well_specified",
        seed=1, model_config_hash="m", truth_config_hash="t", code_version="t",
        sources=tuple(Source(id=s, lon=-103.0, lat=32.0) for s in sources),
        windows=tuple(windows), plans=(), validations=(), utilities=(),
        acquisitions=tuple(acquisitions), beliefs=(), events=(),
    )  # fmt: skip


def test_capacity_report_counts_passes(cfg):
    t = cfg.simulation_epoch_utc
    windows = [_window("w1", "A", t, "p1"), _window("w2", "B", t, "p1"),
               _window("w3", "A", t + timedelta(hours=20), "p2")]  # fmt: skip
    rep = capacity_report(_run(windows), horizon_hours=72.0)
    assert (rep.passes, rep.passes_per_72h, rep.acquisitions) == (2, 2.0, 0)
    assert rep.capacity_to_demand_ratio == 0.0
    assert capacity_report(_run([]), 72.0).acquisitions_per_pass is None


def test_gate_report_text(cfg):
    rep = gate_report("m0_well_specified", [0.10, 0.11, 0.09], [0.20, 0.21, 0.19], [], 72.0)
    assert rep.gate.passed
    assert rep.verdict_text().startswith("G4.5 PASS on m0_well_specified")
