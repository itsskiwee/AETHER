from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from aether.config import BlackoutConfig, load_scenario
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
from aether.planning.cpsat import solve_schedule
from aether.planning.greedy import build_heuristic_plan, greedy_insert
from aether.rng import keyed_rng
from tests.golden.oracle import brute_force_optimum

T0 = datetime(2026, 10, 17, tzinfo=UTC)


def make_window(
    window_id="w1",
    *,
    source_id="s1",
    spacecraft_id="vsat_a",
    start_s=0,
    end_s=None,
    duration_s=3.0,
    orbit=1,
    data_bytes=1,
    energy_wh=0.1,
):
    start = T0 + timedelta(seconds=start_s)
    end = T0 + timedelta(seconds=start_s + duration_s if end_s is None else end_s)
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
        duration_s=duration_s,
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


def test_checker_rejects_selection_missing_from_plan_candidate_set(bundle, geometry_stub):
    window, option_id = make_window()
    plan = make_plan([Selection(window_id=window.id, option_id=option_id)]).model_copy(
        update={"candidate_window_ids": ()}
    )

    result = call(bundle, plan, [window])

    assert "NOT_CANDIDATE" in {item.rule for item in result.violations}


def test_checker_rejects_option_duration_that_disagrees_with_sensor(bundle, geometry_stub):
    window, option_id = make_window()
    original_option = window.options[0]
    shorter_option = original_option.model_copy(
        update={"end_utc": original_option.start_utc + timedelta(seconds=1)}
    )
    window = window.model_copy(update={"options": (shorter_option,)})

    result = call(
        bundle,
        make_plan([Selection(window_id=window.id, option_id=option_id)]),
        [window],
    )

    assert "DURATION" in {item.rule for item in result.violations}


def test_checker_rejects_selection_before_replan_time(bundle, geometry_stub):
    window, option_id = make_window()
    plan = make_plan([Selection(window_id=window.id, option_id=option_id)]).model_copy(
        update={"created_at_sim_utc": T0 + timedelta(seconds=4)}
    )

    result = call(bundle, plan, [window])

    assert "PAST_ACQUISITION" in {item.rule for item in result.violations}


def test_checker_rejects_selection_after_replan_lookahead(bundle, geometry_stub):
    beyond_lookahead_s = int(bundle.model.planner.lookahead_hours * 3600) + 1
    window, _ = make_window()
    option_start = T0 + timedelta(seconds=beyond_lookahead_s)
    option = window.options[0].model_copy(
        update={
            "option_id": acquisition_option_id(window.id, option_start),
            "start_utc": option_start,
            "end_utc": option_start + timedelta(seconds=3),
        }
    )
    window = window.model_copy(
        update={"start_utc": option.start_utc, "end_utc": option.end_utc, "options": (option,)}
    )
    option_id = option.option_id

    result = call(
        bundle,
        make_plan([Selection(window_id=window.id, option_id=option_id)]),
        [window],
    )

    assert "OUTSIDE_LOOKAHEAD" in {item.rule for item in result.violations}


def test_checker_detects_overlapping_observations(bundle, geometry_stub):
    first, first_id = make_window("a", source_id="s1", start_s=0, end_s=3)
    second, second_id = make_window("b", source_id="s2", start_s=2, end_s=5)
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


def test_mutated_orbit_slew_helper_cannot_hide_conflicting_schedule(bundle, monkeypatch):
    first, first_id = make_window("a", source_id="s1", start_s=0, end_s=3)
    second, second_id = make_window("b", source_id="s2", start_s=4, end_s=7)
    utilities = {
        window.id: CandidateUtility(
            window_id=window.id,
            plan_revision=0,
            expected_info_gain_bits=1.0,
            decision_relevance=0.0,
            latency_s=0.0,
            resource_cost=0.0,
            p_valid_forecast=1.0,
            utility=1.0,
            integer_utility=10,
        )
        for window in (first, second)
    }
    monkeypatch.setattr("aether.orbit.slew_time_s", lambda *_: 0.0)
    # greedy imports the helper by value, so mutate its active call-site alias as well.
    monkeypatch.setattr("aether.planning.greedy.slew_time_s", lambda *_: 0.0)
    monkeypatch.setattr(checker, "_load_pinned_eop", lambda: "fixture-eop")
    monkeypatch.setattr(checker, "_build_satellite", lambda _: object())

    def independent_geometry(_satellite, source, _when):
        los = np.array([1.0, 0.0, 0.0]) if source.id == "s1" else np.array([0.0, 1.0, 0.0])
        return 5.0, 20.0, 40.0, los

    monkeypatch.setattr(checker, "_geometry", independent_geometry)
    plan, _ = solve_schedule(
        [first, second],
        utilities,
        bundle.model.spacecraft,
        bundle.model.planner,
        created_at_sim_utc=T0,
    )
    assert len(plan.selections) == 2
    report = check_schedule(
        plan,
        [first, second],
        [Source(id="s1", lon=-103.0, lat=32.0), Source(id="s2", lon=-104.0, lat=33.0)],
        bundle.model.spacecraft,
        bundle.model.sensors["vs_a_point_source"],
        bundle.model,
    )
    assert "SLEW" in {violation.rule for violation in report.violations}


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


def test_checker_detects_per_orbit_limit(bundle, geometry_stub):
    first, first_id = make_window("a", source_id="s1", start_s=0)
    second, second_id = make_window("b", source_id="s2", start_s=10)
    base = bundle.model.spacecraft["vsat_a"]
    constrained = base.model_copy(
        update={"resources": base.resources.model_copy(update={"max_acquisitions_per_orbit": 1})}
    )
    result = check_schedule(
        make_plan(
            [
                Selection(window_id="a", option_id=first_id),
                Selection(window_id="b", option_id=second_id),
            ]
        ),
        [first, second],
        [Source(id="s1", lon=-103.0, lat=32.0), Source(id="s2", lon=-104.0, lat=33.0)],
        {**bundle.model.spacecraft, "vsat_a": constrained},
        bundle.model.sensors["vs_a_point_source"],
        bundle.model,
    )
    assert "PER_ORBIT_LIMIT" in {item.rule for item in result.violations}


def test_checker_rejects_selected_option_in_infeasible_window(bundle, geometry_stub):
    window, option_id = make_window()
    window = window.model_copy(update={"feasible": False})
    plan = make_plan([Selection(window_id=window.id, option_id=option_id)])
    result = call(bundle, plan, [window])
    assert "INFEASIBLE_WINDOW" in {item.rule for item in result.violations}


def test_checker_rejects_acquisition_overlapping_spacecraft_blackout(bundle, geometry_stub):
    window, option_id = make_window()
    option = window.options[0]
    base = bundle.model.spacecraft[window.spacecraft_id]
    blackout = BlackoutConfig(
        start_utc=option.start_utc + timedelta(seconds=1),
        end_utc=option.end_utc + timedelta(seconds=1),
        reason="injected maintenance",
    )
    spacecraft = {
        **bundle.model.spacecraft,
        base.id: base.model_copy(update={"blackouts": (blackout,)}),
    }

    report = check_schedule(
        make_plan([Selection(window_id=window.id, option_id=option_id)]),
        [window],
        [Source(id="s1", lon=-103, lat=32)],
        spacecraft,
        bundle.model.sensors["vs_a_point_source"],
        bundle.model,
    )

    assert "BLACKOUT" in {item.rule for item in report.violations}


def test_checker_rejects_sensor_not_carried_by_spacecraft(bundle, geometry_stub):
    window, option_id = make_window()
    base = bundle.model.spacecraft[window.spacecraft_id]
    spacecraft = {
        **bundle.model.spacecraft,
        base.id: base.model_copy(update={"sensor_ids": ()}),
    }

    report = check_schedule(
        make_plan([Selection(window_id=window.id, option_id=option_id)]),
        [window],
        [Source(id="s1", lon=-103, lat=32)],
        spacecraft,
        bundle.model.sensors["vs_a_point_source"],
        bundle.model,
    )

    assert "UNKNOWN_SENSOR" in {item.rule for item in report.violations}


def test_checker_includes_committed_acquisitions_in_conflict_checks(bundle, geometry_stub):
    candidate, candidate_id = make_window("candidate", source_id="s1", start_s=0, end_s=3)
    fixed, fixed_id = make_window("fixed", source_id="s2", start_s=2, end_s=5)
    result = check_schedule(
        make_plan([Selection(window_id="candidate", option_id=candidate_id)]),
        [candidate],
        [Source(id="s1", lon=-103.0, lat=32.0), Source(id="s2", lon=-104.0, lat=33.0)],
        bundle.model.spacecraft,
        bundle.model.sensors["vs_a_point_source"],
        bundle.model,
        committed=[fixed],
        committed_selections=[Selection(window_id="fixed", option_id=fixed_id)],
    )
    assert "NO_OVERLAP" in {item.rule for item in result.violations}


def test_checker_reports_missing_committed_selection(bundle, geometry_stub):
    fixed, _ = make_window("fixed")
    result = check_schedule(
        make_plan([]),
        [],
        [Source(id="s1", lon=-103.0, lat=32.0)],
        bundle.model.spacecraft,
        bundle.model.sensors["vs_a_point_source"],
        bundle.model,
        committed=[fixed],
    )
    assert "COMMITTED_ACQUISITION" in {item.rule for item in result.violations}


def test_checker_revalidates_slew_from_committed_acquisition_on_replan(bundle, monkeypatch):
    fixed, fixed_id = make_window("fixed", source_id="s1", start_s=0, end_s=3)
    candidate, candidate_id = make_window("candidate", source_id="s2", start_s=4, end_s=7)
    monkeypatch.setattr(checker, "_load_pinned_eop", lambda: "fixture-eop")
    monkeypatch.setattr(checker, "_build_satellite", lambda _: object())

    def geometry(_satellite, source, _when):
        los = np.array([1.0, 0.0, 0.0]) if source.id == "s1" else np.array([0.0, 1.0, 0.0])
        return 5.0, 20.0, 40.0, los

    monkeypatch.setattr(checker, "_geometry", geometry)
    plan = make_plan([Selection(window_id=candidate.id, option_id=candidate_id)]).model_copy(
        update={"created_at_sim_utc": T0 + timedelta(seconds=3)}
    )

    result = check_schedule(
        plan,
        [candidate],
        [Source(id="s1", lon=-103, lat=32), Source(id="s2", lon=-104, lat=33)],
        bundle.model.spacecraft,
        bundle.model.sensors["vs_a_point_source"],
        bundle.model,
        committed=[fixed],
        committed_selections=[Selection(window_id=fixed.id, option_id=fixed_id)],
    )

    assert "SLEW" in {item.rule for item in result.violations}


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
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not any(
        name.startswith(("aether.orbit", "aether.planning.cpsat", "aether.planning.policies"))
        for name in imported
    )


def test_capacity_witness_does_not_import_solver_or_policy_modules(repo_root):
    import ast
    from pathlib import Path

    source = Path(repo_root) / "scripts/feasibility/capacity_witness.py"
    tree = ast.parse(source.read_text())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not any(
        name.startswith(
            ("aether.planning.cpsat", "aether.planning.policies", "aether.planning.greedy")
        )
        for name in imported
    )


def test_raw_sgp4_astropy_geometry_uses_pinned_eop(repo_root, bundle):
    satellite = checker._build_satellite(bundle.model.spacecraft["vsat_a"])
    source = Source(id="geometry-probe", lon=-103.0, lat=32.0)
    when = checker.Time("2026-10-17T00:00:00", scale="utc")
    table = checker._load_pinned_eop()

    off_nadir_deg, elevation_deg, sun_elevation_deg, los = checker._geometry(
        satellite, source, when
    )

    assert table is not None
    assert all(np.isfinite(value) for value in (off_nadir_deg, elevation_deg, sun_elevation_deg))
    assert np.isclose(np.linalg.norm(los), 1.0)
    assert (repo_root / "data/eop/finals2000A.all").is_file()


def test_brute_force_oracle_selects_highest_utility_feasible_option(bundle, geometry_stub):
    first, _ = make_window("a", source_id="s1", start_s=0, end_s=3)
    second, second_id = make_window("b", source_id="s2", start_s=0, end_s=3)
    utilities = {
        "a": CandidateUtility(
            window_id="a",
            plan_revision=0,
            expected_info_gain_bits=1.0,
            decision_relevance=0,
            latency_s=0,
            resource_cost=0,
            p_valid_forecast=1,
            utility=1,
            integer_utility=10,
        ),
        "b": CandidateUtility(
            window_id="b",
            plan_revision=0,
            expected_info_gain_bits=2.0,
            decision_relevance=0,
            latency_s=0,
            resource_cost=0,
            p_valid_forecast=1,
            utility=2,
            integer_utility=20,
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


def test_solver_matches_oracle_and_random_schedules_on_500_instances(bundle, geometry_stub):
    """Stub geometry isolates scheduling; it is not orbit validation evidence."""
    sources = [Source(id=f"s{i}", lon=-103.0 + i * 0.1, lat=32.0) for i in range(6)]
    for instance in range(500):
        rng = keyed_rng(20261017, "placement", "l8_oracle", instance)
        count = int(rng.integers(1, 7))
        duration_s = int(rng.integers(3, 14))
        sensor_profile = bundle.model.sensors["vs_a_point_source"].model_copy(
            update={"exposure_seconds": duration_s}
        )
        windows = []
        utilities = {}
        for index in range(count):
            start_s = int(rng.integers(0, 100))
            source_id = f"s{int(rng.integers(0, len(sources)))}"
            window, _ = make_window(
                f"i{instance}-w{index}",
                source_id=source_id,
                start_s=start_s,
                end_s=start_s + duration_s,
                duration_s=duration_s,
                data_bytes=1,
                energy_wh=0.1,
            )
            windows.append(window)
            integer_utility = int(rng.integers(1, 100))
            utilities[window.id] = CandidateUtility(
                window_id=window.id,
                plan_revision=0,
                expected_info_gain_bits=1.0,
                decision_relevance=0.0,
                latency_s=0.0,
                resource_cost=0.0,
                p_valid_forecast=1.0,
                utility=float(integer_utility),
                integer_utility=integer_utility,
            )

        oracle = brute_force_optimum(
            windows,
            utilities,
            sources,
            bundle.model.spacecraft,
            sensor_profile,
            bundle.model,
        )
        plan, _ = solve_schedule(
            windows,
            utilities,
            bundle.model.spacecraft,
            bundle.model.planner,
            run_id=f"l8-{instance}",
            created_at_sim_utc=T0,
            random_seed=instance,
        )
        solved_integer_utility = round(
            (plan.objective_value or 0.0) * bundle.model.planner.utility_integer_scale
        )
        assert solved_integer_utility == oracle.objective_value, instance
        report = check_schedule(
            plan,
            windows,
            sources,
            bundle.model.spacecraft,
            sensor_profile,
            bundle.model,
        )
        assert report.ok, (instance, report.violations)

        order = [windows[index].id for index in rng.permutation(len(windows))]
        greedy_selections, _ = greedy_insert(
            windows,
            order,
            utilities,
            bundle.model.spacecraft,
            bundle.model.planner,
            (),
        )
        greedy_plan = build_heuristic_plan(
            run_id=f"l8-greedy-{instance}",
            policy_id=PolicyId.GREEDY_EIG,
            revision=0,
            created_at_sim_utc=T0,
            cause="l8 randomized schedule check",
            planner_cfg=bundle.model.planner,
            windows=windows,
            selections=greedy_selections,
        )
        greedy_report = check_schedule(
            greedy_plan,
            windows,
            sources,
            bundle.model.spacecraft,
            sensor_profile,
            bundle.model,
        )
        assert greedy_report.ok, (instance, greedy_report.violations)


@pytest.mark.parametrize("completed", [False, True])
def test_completed_commitment_releases_source_cap_but_remains_in_resources(
    bundle, geometry_stub, completed
):
    fixed, fixed_id = make_window("past", source_id="s1", start_s=0)
    candidate, candidate_id = make_window("future", source_id="s1", start_s=30)
    plan = make_plan([Selection(window_id=candidate.id, option_id=candidate_id)])
    if completed:
        plan = plan.model_copy(update={"created_at_sim_utc": T0 + timedelta(seconds=10)})
    result = check_schedule(
        plan,
        [candidate],
        [Source(id="s1", lon=-103, lat=32)],
        bundle.model.spacecraft,
        bundle.model.sensors["vs_a_point_source"],
        bundle.model,
        committed=[fixed],
        committed_selections=[Selection(window_id=fixed.id, option_id=fixed_id)],
    )
    assert ("SOURCE_LIMIT" in {v.rule for v in result.violations}) is not completed
    if completed:
        assert result.ok
    oversized = fixed.model_copy(
        update={"data_bytes": bundle.model.spacecraft["vsat_a"].resources.storage_bytes}
    )
    constrained = check_schedule(
        plan,
        [candidate],
        [Source(id="s1", lon=-103, lat=32)],
        bundle.model.spacecraft,
        bundle.model.sensors["vs_a_point_source"],
        bundle.model,
        committed=[oversized],
        committed_selections=[Selection(window_id=fixed.id, option_id=fixed_id)],
    )
    assert "STORAGE" in {v.rule for v in constrained.violations}


def test_sgp4_propagates_at_utc_and_leaves_ut1_for_frame_rotation(bundle):
    """Official Astropy SGP4/TEME recipe: UTC propagation, IERS frame rotation.

    https://docs.astropy.org/en/stable/coordinates/satellites.html
    The deliberately nonzero DUT1 makes the former UT1 propagation fail this oracle.
    """
    import astropy.units as u
    from astropy.coordinates import ITRS, TEME, CartesianRepresentation
    from astropy.time import Time
    from astropy.utils import iers
    from sgp4.api import jday

    when = Time(T0, scale="utc")
    when.delta_ut1_utc = 0.75
    satellite = checker._build_satellite(bundle.model.spacecraft["vsat_a"])
    jd, fraction = jday(T0.year, T0.month, T0.day, T0.hour, T0.minute, T0.second)
    error, position, _ = satellite.sgp4(jd, fraction)
    assert error == 0
    with iers.earth_orientation_table.set(checker._load_pinned_eop()):
        expected = (
            TEME(CartesianRepresentation(np.asarray(position) * u.km), obstime=when)
            .transform_to(ITRS(obstime=when))
            .cartesian.xyz.to_value(u.km)
        )
        actual = checker._satellite_itrs_km(satellite, when)
    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-9)
