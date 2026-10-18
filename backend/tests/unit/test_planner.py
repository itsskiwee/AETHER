from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from aether.config import load_scenario
from aether.contracts.enums import PolicyId
from aether.contracts.models import (
    AcquisitionOption,
    CandidateUtility,
    ObservationWindow,
    Selection,
    Source,
    acquisition_option_id,
)
from aether.planning import checker
from aether.planning.context import PlanningContext
from aether.planning.cpsat import solve_schedule
from aether.planning.greedy import build_heuristic_plan, greedy_insert, rejection_reasons
from aether.planning.policies import (
    AdaptiveEig,
    FirstFeasible,
    GreedyEig,
    LargestFirst,
    RandomFeasible,
    StaticPriority,
)
from tests.golden.oracle import brute_force_optimum

T0 = datetime(2026, 10, 17, tzinfo=UTC)


def make_window(
    window_id,
    *,
    source_id=None,
    spacecraft_id="vsat_a",
    option_starts=(0,),
    orbit=1,
    data_bytes=1,
    energy_wh=0.1,
):
    source_id = source_id or f"source-{window_id}"
    options = []
    for start_seconds in option_starts:
        start = T0 + timedelta(seconds=start_seconds)
        end = start + timedelta(seconds=3)
        options.append(
            AcquisitionOption(
                option_id=acquisition_option_id(window_id, start),
                window_id=window_id,
                start_utc=start,
                end_utc=end,
                off_nadir_deg=5.0,
                sun_elevation_deg=40.0,
                los_unit_ecef=(1.0, 0.0, 0.0),
            )
        )
    return ObservationWindow(
        id=window_id,
        spacecraft_id=spacecraft_id,
        sensor_id="vs_a_point_source",
        source_id=source_id,
        start_utc=T0,
        end_utc=T0 + timedelta(seconds=max(option_starts) + 10),
        pass_id="test-pass",
        orbit_number=orbit,
        feasible=True,
        rejection_reasons=(),
        min_off_nadir_deg=5.0,
        options=tuple(options),
        duration_s=3.0,
        energy_wh=energy_wh,
        data_bytes=data_bytes,
    )


def utility(window_id, integer_utility=100):
    scale = 10_000
    return CandidateUtility(
        window_id=window_id,
        plan_revision=0,
        expected_info_gain_bits=integer_utility / scale,
        decision_relevance=0.0,
        latency_s=0.0,
        resource_cost=0.0,
        p_valid_forecast=1.0,
        utility=integer_utility / scale,
        integer_utility=integer_utility,
    )


def make_context(bundle, windows, utilities, *, revision=0):
    return PlanningContext(
        run_id="planner-test",
        revision=revision,
        now_utc=T0,
        cause="plan_requested",
        cfg=bundle.model,
        windows=tuple(windows),
        committed=(),
        utilities=utilities,
        posterior_mean_flux_kg_h={window.source_id: 100.0 for window in windows},
        p_active_by_source={window.source_id: 0.5 for window in windows},
    )


@pytest.fixture
def bundle(repo_root):
    return load_scenario(repo_root / "configs/base.yaml")


@pytest.fixture
def geometry_stub(monkeypatch):
    monkeypatch.setattr(checker, "_load_pinned_eop", lambda: "test-eop")
    monkeypatch.setattr(checker, "_build_satellite", lambda _profile: object())
    monkeypatch.setattr(
        checker,
        "_geometry",
        lambda *_args: (5.0, 20.0, 40.0, np.array([1.0, 0.0, 0.0])),
    )


def test_committed_acquisition_counts_toward_source_limit(bundle):
    committed = make_window("committed", source_id="same-source", option_starts=(0,))
    candidate = make_window("candidate", source_id="same-source", option_starts=(100,))
    committed_selection = Selection(
        window_id=committed.id, option_id=committed.options[0].option_id
    )
    utilities = {candidate.id: utility(candidate.id)}

    plan, _ = solve_schedule(
        [candidate],
        utilities,
        bundle.model.spacecraft,
        bundle.model.planner,
        [committed],
        committed_selections=[committed_selection],
        created_at_sim_utc=T0,
        random_seed=1000,
    )
    greedy, _ = greedy_insert(
        [candidate],
        [candidate.id],
        utilities,
        bundle.model.spacecraft,
        bundle.model.planner,
        [committed],
        [committed_selection],
        now_utc=T0,
    )

    assert plan.selections == ()
    assert greedy == ()


@pytest.mark.parametrize("now_seconds,expected_count", [(2, 0), (3, 1), (4, 1)])
@pytest.mark.parametrize("fixed_spacecraft", ["vsat_a", "vsat_b"])
def test_source_limit_excludes_completed_history_only(
    bundle, now_seconds, expected_count, fixed_spacecraft
):
    fixed = make_window(
        "completed",
        source_id="same-source",
        spacecraft_id=fixed_spacecraft,
        option_starts=(0,),
    )
    candidate = make_window("revisit", source_id="same-source", option_starts=(100,))
    selection = Selection(window_id=fixed.id, option_id=fixed.options[0].option_id)
    utilities = {candidate.id: utility(candidate.id)}
    now = T0 + timedelta(seconds=now_seconds)
    plan, _ = solve_schedule(
        [candidate],
        utilities,
        bundle.model.spacecraft,
        bundle.model.planner,
        [fixed],
        committed_selections=[selection],
        created_at_sim_utc=now,
    )
    greedy, _ = greedy_insert(
        [candidate],
        [candidate.id],
        utilities,
        bundle.model.spacecraft,
        bundle.model.planner,
        [fixed],
        [selection],
        now_utc=now,
    )
    assert len(plan.selections) == len(greedy) == expected_count
    reasons = rejection_reasons(
        [candidate],
        (),
        utilities,
        bundle.model.planner,
        bundle.model.spacecraft,
        [fixed],
        [selection],
        now_utc=now,
    )
    assert reasons[candidate.id] == ("SOURCE_LIMIT" if expected_count == 0 else "NOT_SELECTED")


def test_completed_history_still_constrains_slew(bundle):
    fixed = make_window("completed", option_starts=(0,))
    candidate = make_window("too-soon", option_starts=(4,))
    selection = Selection(window_id=fixed.id, option_id=fixed.options[0].option_id)
    utilities = {candidate.id: utility(candidate.id)}
    now = T0 + timedelta(seconds=3)
    plan, _ = solve_schedule(
        [candidate],
        utilities,
        bundle.model.spacecraft,
        bundle.model.planner,
        [fixed],
        committed_selections=[selection],
        created_at_sim_utc=now,
    )
    greedy, _ = greedy_insert(
        [candidate],
        [candidate.id],
        utilities,
        bundle.model.spacecraft,
        bundle.model.planner,
        [fixed],
        [selection],
        now_utc=now,
    )
    assert plan.selections == greedy == ()
    assert (
        rejection_reasons(
            [candidate],
            (),
            utilities,
            bundle.model.planner,
            bundle.model.spacecraft,
            [fixed],
            [selection],
            now_utc=now,
        )[candidate.id]
        == "CONFLICT"
    )


@pytest.mark.parametrize("policy_type", [LargestFirst, AdaptiveEig, GreedyEig, StaticPriority])
def test_policy_passes_simulation_time_for_revisits(bundle, policy_type):
    fixed = make_window("old", source_id="same-source", option_starts=(0,))
    candidate = make_window("new", source_id="same-source", option_starts=(100,))
    ctx = make_context(bundle, [candidate], {candidate.id: utility(candidate.id)})
    ctx = replace(
        ctx,
        now_utc=T0 + timedelta(seconds=3),
        committed=(fixed,),
        committed_selections=(Selection(window_id=fixed.id, option_id=fixed.options[0].option_id),),
    )
    assert len(policy_type().plan(ctx).selections) == 1


@pytest.mark.parametrize(
    ("resource_changes", "fixed_energy", "candidate_energy", "fixed_bytes", "candidate_bytes"),
    [
        ({"max_acquisitions_per_orbit": 1}, 0.1, 0.1, 1, 1),
        ({"storage_bytes": 1}, 0.1, 0.1, 1, 1),
        (
            {
                "battery_capacity_wh": 2.0,
                "min_state_of_charge": 0.0,
                "initial_state_of_charge": 0.5,
                "orbit_average_recharge_wh": 0.0,
            },
            0.6,
            0.6,
            1,
            1,
        ),
    ],
)
@pytest.mark.parametrize("now_seconds", [0, 3])
def test_committed_acquisition_counts_toward_orbit_budgets(
    now_seconds,
    bundle,
    resource_changes,
    fixed_energy,
    candidate_energy,
    fixed_bytes,
    candidate_bytes,
):
    committed = make_window(
        "committed",
        source_id="fixed-source",
        option_starts=(0,),
        energy_wh=fixed_energy,
        data_bytes=fixed_bytes,
    )
    candidate = make_window(
        "candidate",
        source_id="new-source",
        option_starts=(100,),
        energy_wh=candidate_energy,
        data_bytes=candidate_bytes,
    )
    selection = Selection(window_id=committed.id, option_id=committed.options[0].option_id)
    profile = bundle.model.spacecraft["vsat_a"]
    profile = profile.model_copy(
        update={"resources": profile.resources.model_copy(update=resource_changes)}
    )
    spacecraft = {**bundle.model.spacecraft, "vsat_a": profile}
    utilities = {candidate.id: utility(candidate.id)}

    plan, _ = solve_schedule(
        [candidate],
        utilities,
        spacecraft,
        bundle.model.planner,
        [committed],
        committed_selections=[selection],
        created_at_sim_utc=T0 + timedelta(seconds=now_seconds),
        random_seed=1000,
    )
    greedy, _ = greedy_insert(
        [candidate],
        [candidate.id],
        utilities,
        spacecraft,
        bundle.model.planner,
        [committed],
        [selection],
        now_utc=T0 + timedelta(seconds=now_seconds),
    )

    assert plan.selections == ()
    assert greedy == ()


def test_energy_coefficients_are_scoped_to_their_spacecraft(bundle):
    first_profile = bundle.model.spacecraft["vsat_a"].model_copy(
        update={
            "resources": bundle.model.spacecraft["vsat_a"].resources.model_copy(
                update={
                    "battery_capacity_wh": 10.0,
                    "min_state_of_charge": 0.0,
                    "initial_state_of_charge": 0.5,
                    "orbit_average_recharge_wh": 0.0,
                }
            )
        }
    )
    second_profile = bundle.model.spacecraft["vsat_b"].model_copy(
        update={"resources": first_profile.resources}
    )
    spacecraft = {
        **bundle.model.spacecraft,
        "vsat_a": first_profile,
        "vsat_b": second_profile,
    }
    expensive = make_window("a-expensive", spacecraft_id="vsat_a", energy_wh=6.0)
    affordable = make_window("b-affordable", spacecraft_id="vsat_b", energy_wh=0.1)

    plan, _ = solve_schedule(
        [expensive, affordable],
        {expensive.id: utility(expensive.id, 200), affordable.id: utility(affordable.id, 100)},
        spacecraft,
        bundle.model.planner,
        created_at_sim_utc=T0,
        random_seed=1000,
    )

    assert [selection.window_id for selection in plan.selections] == [affordable.id]


def test_greedy_rechecks_later_energy_prefixes_after_earlier_insert(bundle):
    profile = bundle.model.spacecraft["vsat_a"].model_copy(
        update={
            "resources": bundle.model.spacecraft["vsat_a"].resources.model_copy(
                update={
                    "battery_capacity_wh": 10.0,
                    "min_state_of_charge": 0.0,
                    "initial_state_of_charge": 0.6,
                    "orbit_average_recharge_wh": 1.0,
                }
            )
        }
    )
    spacecraft = {**bundle.model.spacecraft, "vsat_a": profile}
    later = make_window("later", orbit=2, option_starts=(100,), energy_wh=5.5)
    earlier = make_window("earlier", orbit=1, option_starts=(0,), energy_wh=2.1)

    selections, _ = greedy_insert(
        [later, earlier],
        [later.id, earlier.id],
        {later.id: utility(later.id, 200), earlier.id: utility(earlier.id, 100)},
        spacecraft,
        bundle.model.planner,
        (),
        now_utc=T0,
    )

    assert [selection.window_id for selection in selections] == [later.id]


def test_rejection_reason_checks_temporal_conflict_and_lower_rank_fallback(bundle):
    selected = make_window("selected", option_starts=(0,))
    candidate = make_window("candidate", option_starts=(1, 20))
    blocked = make_window("blocked", option_starts=(1,))
    selections = [Selection(window_id=selected.id, option_id=selected.options[0].option_id)]
    utilities = {w.id: utility(w.id) for w in (selected, candidate, blocked)}

    reasons = rejection_reasons(
        [selected, candidate, blocked],
        selections,
        utilities,
        bundle.model.planner,
        bundle.model.spacecraft,
        now_utc=T0,
    )

    assert reasons[candidate.id] == "NOT_SELECTED"
    assert reasons[blocked.id] == "CONFLICT"


@pytest.mark.parametrize(
    "policy_type",
    [AdaptiveEig, FirstFeasible, GreedyEig, LargestFirst, RandomFeasible, StaticPriority],
)
def test_policy_replay_is_deterministic_and_plan_runtime_is_stable(bundle, policy_type):
    window = make_window("policy", option_starts=(10, 30))
    ctx = make_context(bundle, [window], {window.id: utility(window.id, 500)})

    first = policy_type().plan(ctx)
    second = policy_type().plan(ctx)

    assert first.selections == second.selections
    assert first.runtime_s is None and second.runtime_s is None


def test_static_priority_freezes_revision_zero_values(bundle):
    window = make_window("static", option_starts=(10,))
    policy = StaticPriority()
    first_context = make_context(bundle, [window], {window.id: utility(window.id, 500)})
    policy.plan(first_context)
    revised_utility = utility(window.id, 100)
    revised = make_context(bundle, [window], {window.id: revised_utility}, revision=1)

    plan = policy.plan(revised)

    assert plan.selections == (
        Selection(window_id=window.id, option_id=window.options[0].option_id),
    )
    assert policy.last_rejection_reasons == {}


def test_random_feasible_is_independent_of_window_input_order(bundle):
    windows = [make_window(window_id) for window_id in ("random-a", "random-b", "random-c")]
    utilities = {window.id: utility(window.id, 100) for window in windows}

    forward = RandomFeasible().plan(make_context(bundle, windows, utilities))
    reverse = RandomFeasible().plan(make_context(bundle, list(reversed(windows)), utilities))

    assert forward.selections == reverse.selections


def test_first_feasible_skips_windows_before_request_arrival(bundle, monkeypatch):
    before = make_window("before", source_id="request-source", option_starts=(3600,))
    after = make_window("after", source_id="request-source", option_starts=(50_000,))

    class FixedArrivalRng:
        def poisson(self, _mean):
            return 1

        def uniform(self, _low, _high, _size):
            return np.array([0.5])

    monkeypatch.setattr("aether.planning.policies.keyed_rng", lambda *_args: FixedArrivalRng())
    utilities = {window.id: utility(window.id, 100) for window in (before, after)}
    policy = FirstFeasible()

    plan = policy.plan(make_context(bundle, [before, after], utilities))

    assert [selection.window_id for selection in plan.selections] == [after.id]


def test_cp_sat_objective_matches_independent_oracle_on_200_small_instances(bundle, geometry_stub):
    random = np.random.default_rng(20261017)
    base_profile = bundle.model.spacecraft["vsat_a"]
    for instance in range(200):
        count = int(random.integers(1, 13))
        windows = []
        sources = []
        utilities = {}
        for index in range(count):
            window_id = f"i{instance}-w{index}"
            source_id = f"i{instance}-s{index}"
            window = make_window(
                window_id,
                source_id=source_id,
                option_starts=(int(random.integers(0, 240)),),
                orbit=int(random.integers(1, 4)),
                data_bytes=int(random.integers(1, 5)),
                energy_wh=float(random.integers(1, 31)) / 10,
            )
            windows.append(window)
            sources.append(Source(id=source_id, lon=-103.0, lat=32.0))
            utilities[window_id] = utility(window_id, int(random.integers(10, 1001)))
        resources = base_profile.resources.model_copy(
            update={
                "battery_capacity_wh": 10.0,
                "min_state_of_charge": 0.2,
                "initial_state_of_charge": 0.6,
                "orbit_average_recharge_wh": 1.0,
                "storage_bytes": int(random.integers(4, 16)),
                "max_acquisitions_per_orbit": int(random.integers(1, 5)),
            }
        )
        profile = base_profile.model_copy(update={"resources": resources})
        spacecraft = {**bundle.model.spacecraft, "vsat_a": profile}

        plan, _ = solve_schedule(
            windows,
            utilities,
            spacecraft,
            bundle.model.planner,
            created_at_sim_utc=T0,
            random_seed=instance,
        )
        oracle = brute_force_optimum(
            windows,
            utilities,
            sources,
            spacecraft,
            bundle.model.sensors["vs_a_point_source"],
            bundle.model,
        )

        assert plan.solver_status.value == "OPTIMAL"
        assert plan.objective_value <= plan.best_bound + 1e-12
        assert plan.runtime_s is None
        assert round(plan.objective_value * bundle.model.planner.utility_integer_scale) == (
            oracle.objective_value
        )
        assert checker.check_schedule(
            plan,
            windows,
            sources,
            spacecraft,
            bundle.model.sensors["vs_a_point_source"],
            bundle.model,
        ).ok

        greedy_selections, _ = greedy_insert(
            windows,
            sorted(window.id for window in windows),
            utilities,
            spacecraft,
            bundle.model.planner,
            (),
            now_utc=T0,
        )
        greedy_plan = build_heuristic_plan(
            run_id="planner-test",
            policy_id=PolicyId.GREEDY_EIG,
            revision=0,
            created_at_sim_utc=T0,
            cause="randomized feasibility check",
            planner_cfg=bundle.model.planner,
            windows=windows,
            selections=greedy_selections,
        )
        assert checker.check_schedule(
            greedy_plan,
            windows,
            sources,
            spacecraft,
            bundle.model.sensors["vs_a_point_source"],
            bundle.model,
        ).ok


def test_greedy_helpers_require_the_replan_time(bundle):
    """C2-04 bug class: a missing now_utc silently counted completed looks against the cap."""
    window = make_window("only", option_starts=(0,))
    utilities = {window.id: utility(window.id)}
    args = ([window], [window.id], utilities, bundle.model.spacecraft, bundle.model.planner, ())
    with pytest.raises(TypeError):
        greedy_insert(*args)
    with pytest.raises(TypeError, match="now_utc"):
        greedy_insert(*args, now_utc=None)
    with pytest.raises(TypeError, match="now_utc"):
        rejection_reasons([window], (), utilities, bundle.model.planner, now_utc=None)


def test_completed_commitment_keeps_resources_but_releases_the_source_cap(bundle):
    """After a committed look ends it no longer counts toward PR-O03, but stays on the timeline."""
    cap = bundle.model.planner.max_visits_per_source_per_solve
    done = [
        make_window(f"done-{i}", source_id="same-source", option_starts=(i * 200,))
        for i in range(cap)
    ]
    done_selections = [Selection(window_id=w.id, option_id=w.options[0].option_id) for w in done]
    candidate = make_window("next", source_id="same-source", option_starts=(cap * 200 + 100,))
    overlapping = make_window("overlap", source_id="other-source", option_starts=(0,))
    utilities = {w.id: utility(w.id) for w in (candidate, overlapping)}
    args = (
        [candidate, overlapping],
        [candidate.id, overlapping.id],
        utilities,
        bundle.model.spacecraft,
        bundle.model.planner,
        done,
        done_selections,
    )
    before = greedy_insert(*args, now_utc=T0)[0]
    after = greedy_insert(*args, now_utc=T0 + timedelta(seconds=cap * 200))[0]
    assert candidate.id not in {s.window_id for s in before}
    assert candidate.id in {s.window_id for s in after}
    # The completed acquisition still occupies its time slot for slew/overlap.
    assert overlapping.id not in {s.window_id for s in after}
