from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from aether.config import load_scenario
from aether.contracts.enums import PolicyId, SolverStatus
from aether.contracts.models import (
    AcquisitionOption,
    CandidateUtility,
    ObservationWindow,
    Plan,
    Selection,
    Source,
    acquisition_option_id,
)
from aether.planning import checker
from aether.planning.checker import check_schedule
from tests.golden.oracle import brute_force_optimum

T0 = datetime(2026, 10, 17, tzinfo=UTC)


def make_window(
    window_id="w1",
    *,
    source_id="s1",
    spacecraft_id="vsat_a",
    start_s=0,
    end_s=3,
    orbit=1,
    data_bytes=1,
    energy_wh=0.1,
):
    start = T0 + timedelta(seconds=start_s)
    end = T0 + timedelta(seconds=end_s)
    option_id = acquisition_option_id(window_id, start)
    option = AcquisitionOption(
        option_id=option_id,
        window_id=window_id,
        start_utc=start,
        end_utc=end,
        off_nadir_deg=5.0,
        sun_elevation_deg=40.0,
        los_unit_ecef=(1.0, 0.0, 0.0),
    )
    window = ObservationWindow(
        id=window_id,
        spacecraft_id=spacecraft_id,
        sensor_id="vs_a_point_source",
        source_id=source_id,
        start_utc=T0,
        end_utc=T0 + timedelta(minutes=2),
        pass_id="pass1",
        orbit_number=orbit,
        feasible=True,
        rejection_reasons=(),
        min_off_nadir_deg=5.0,
        options=(option,),
        duration_s=3.0,
        energy_wh=energy_wh,
        data_bytes=data_bytes,
    )
    return window, option_id


def make_plan(selections):
    return Plan(
        run_id="test-run",
        policy_id=PolicyId.LARGEST_FIRST,
        revision=0,
        created_at_sim_utc=T0,
        cause="test",
        objective_weights={},
        candidate_window_ids=tuple(selection.window_id for selection in selections),
        selections=tuple(selections),
        solver_status=SolverStatus.OPTIMAL,
        objective_value=0.0,
        best_bound=0.0,
        runtime_s=0.0,
    )


@pytest.fixture
def bundle(repo_root):
    return load_scenario(repo_root / "configs/base.yaml")


@pytest.fixture
def geometry_stub(monkeypatch):
    monkeypatch.setattr(checker, "_load_pinned_eop", lambda: "fixture-eop")
    monkeypatch.setattr(checker, "_build_satellite", lambda _: object())
    monkeypatch.setattr(
        checker,
        "_geometry",
        lambda *_args: (5.0, 20.0, 40.0, np.array([1.0, 0.0, 0.0])),
    )


def call(bundle, plan, windows):
    return check_schedule(
        plan,
        windows,
        [Source(id="s1", lon=-103.0, lat=32.0), Source(id="s2", lon=-104.0, lat=33.0)],
        bundle.model.spacecraft,
        bundle.model.sensors["vs_a_point_source"],
        bundle.model,
    )


def test_checker_accepts_feasible_schedule(bundle, geometry_stub):
    window, option_id = make_window()
    plan = make_plan([Selection(window_id=window.id, option_id=option_id)])
    result = call(bundle, plan, [window])
    assert result.ok
    assert result.violations == ()


def test_wrong_parent_window_reports_unknown_option(bundle, geometry_stub):
    window, option_id = make_window("w1")
    plan = make_plan([Selection(window_id="w2", option_id=option_id)])
    result = call(bundle, plan, [window])
    assert "UNKNOWN_WINDOW" in {item.rule for item in result.violations}
    assert "UNKNOWN_OPTION" in {item.rule for item in result.violations}


def test_checker_detects_overlapping_observations(bundle, geometry_stub):
    first, first_id = make_window("a", source_id="s1", start_s=0, end_s=4)
    second, second_id = make_window("b", source_id="s2", start_s=2, end_s=6)
    result = call(
        bundle,
        make_plan(
            [
                Selection(window_id="a", option_id=first_id),
                Selection(window_id="b", option_id=second_id),
            ]
        ),
        [first, second],
    )
    assert "NO_OVERLAP" in {item.rule for item in result.violations}


def test_checker_recomputes_slew_from_endpoint_geometry(bundle, monkeypatch):
    first, first_id = make_window("a", source_id="s1", start_s=0, end_s=3)
    second, second_id = make_window("b", source_id="s2", start_s=4, end_s=7)
    monkeypatch.setattr(checker, "_load_pinned_eop", lambda: "fixture-eop")
    monkeypatch.setattr(checker, "_build_satellite", lambda _: object())
    geometry_calls = []

    def geometry(_sat, source, when):
        geometry_calls.append((source.id, when.to_datetime(timezone=UTC)))
        if source.id == "s1":
            los = np.array([1.0, 0.0, 0.0])
        else:
            los = np.array([0.0, 1.0, 0.0])
        return 5.0, 20.0, 40.0, los

    monkeypatch.setattr(checker, "_geometry", geometry)
    result = call(
        bundle,
        make_plan(
            [
                Selection(window_id="a", option_id=first_id),
                Selection(window_id="b", option_id=second_id),
            ]
        ),
        [first, second],
    )
    assert "SLEW" in {item.rule for item in result.violations}
    assert len(geometry_calls) == 4
    assert {when for _, when in geometry_calls} == {
        first.options[0].start_utc,
        first.options[0].end_utc,
        second.options[0].start_utc,
        second.options[0].end_utc,
    }


def test_checker_checks_source_visit_limit_and_resources(bundle, geometry_stub):
    first, first_id = make_window("a", source_id="s1", start_s=0, data_bytes=2, energy_wh=100)
    second, second_id = make_window("b", source_id="s1", start_s=100, data_bytes=2, energy_wh=100)
    plan = make_plan(
        [
            Selection(window_id="a", option_id=first_id),
            Selection(window_id="b", option_id=second_id),
        ]
    )
    base = bundle.model.spacecraft["vsat_a"]
    constrained = base.model_copy(
        update={"resources": base.resources.model_copy(update={"storage_bytes": 1})}
    )
    profiles = {**bundle.model.spacecraft, "vsat_a": constrained}
    result = check_schedule(
        plan,
        [first, second],
        [Source(id="s1", lon=-103.0, lat=32.0)],
        profiles,
        bundle.model.sensors["vs_a_point_source"],
        bundle.model,
    )
    rules = {item.rule for item in result.violations}
    assert {"SOURCE_LIMIT", "STORAGE", "ENERGY"} <= rules


def test_checker_does_not_import_orbit_optimizer_or_policy_modules():
    import ast
    from pathlib import Path

    source = Path(__file__).parents[2] / "aether/planning/checker.py"
    tree = ast.parse(source.read_text())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not any(
        name.startswith(("aether.orbit", "aether.planning.cpsat", "aether.planning.policies"))
        for name in imported
    )


def test_brute_force_oracle_selects_highest_utility_feasible_option(bundle, geometry_stub):
    first, _ = make_window("a", source_id="s1", start_s=0, end_s=10)
    second, second_id = make_window("b", source_id="s2", start_s=0, end_s=10)
    utilities = {
        "a": CandidateUtility(
            window_id="a", plan_revision=0, expected_info_gain_bits=1.0,
            decision_relevance=0, latency_s=0, resource_cost=0, p_valid_forecast=1,
            utility=1, integer_utility=10,
        ),
        "b": CandidateUtility(
            window_id="b", plan_revision=0, expected_info_gain_bits=2.0,
            decision_relevance=0, latency_s=0, resource_cost=0, p_valid_forecast=1,
            utility=2, integer_utility=20,
        ),
    }
    result = brute_force_optimum(
        [first, second],
        utilities,
        [Source(id="s1", lon=-103.0, lat=32.0), Source(id="s2", lon=-104.0, lat=33.0)],
        bundle.model.spacecraft,
        bundle.model.sensors["vs_a_point_source"],
        bundle.model,
    )
    assert result.selected_option_ids == (second_id,)
    assert result.objective_value == 20
