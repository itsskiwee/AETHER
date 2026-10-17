"""Deterministic CP-SAT acquisition-option scheduling."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from fractions import Fraction
from math import lcm
from time import perf_counter

from ortools.sat.python import cp_model

from aether.config import PlannerConfig, SpacecraftProfile
from aether.contracts.enums import PolicyId, SolverStatus
from aether.contracts.models import CandidateUtility, ObservationWindow, Plan, Selection
from aether.planning.greedy import conflict_pairs, resolve_committed
from aether.rng import derive_seed


def _microseconds(duration) -> int:
    return duration.days * 86_400_000_000 + duration.seconds * 1_000_000 + duration.microseconds


def solve_schedule(
    windows: tuple[ObservationWindow, ...] | list[ObservationWindow],
    utilities: dict[str, CandidateUtility],
    spacecraft: dict[str, SpacecraftProfile],
    planner_cfg: PlannerConfig,
    committed: tuple[ObservationWindow, ...] | list[ObservationWindow] = (),
    *,
    committed_selections: tuple[Selection, ...] | list[Selection] = (),
    run_id: str = "",
    revision: int = 0,
    created_at_sim_utc: datetime | None = None,
    cause: str = "plan_requested",
    policy_id: PolicyId = PolicyId.ADAPTIVE_EIG,
    random_seed: int = 0,
) -> tuple[Plan, dict[str, datetime]]:
    """Maximize integer utility subject to exact option-level temporal/resource constraints."""
    started = perf_counter()
    if created_at_sim_utc is None:
        timestamp_candidates = [w.start_utc for w in (*windows, *committed)]
        created_at_sim_utc = min(
            timestamp_candidates,
            default=datetime(1970, 1, 1, tzinfo=timezone.utc),
        )
    candidates = tuple(sorted((w for w in windows if w.feasible), key=lambda w: w.id))
    committed = tuple(committed)
    committed_selections = tuple(committed_selections)
    pair_conflicts = conflict_pairs(
        candidates, spacecraft, committed, committed_selections
    )
    fixed_option_ids = {selection.option_id for selection in committed_selections}
    active = tuple(
        w for w in candidates
        if w.id in utilities
        and utilities[w.id].expected_info_gain_bits >= planner_cfg.min_utility_bits
        and utilities[w.id].integer_utility > 0
    )
    model = cp_model.CpModel()
    option_vars = {}
    intervals: dict[str, list] = defaultdict(list)

    if not active or not any(w.options for w in active):
        plan = Plan(
            run_id=run_id, policy_id=policy_id, revision=revision,
            created_at_sim_utc=created_at_sim_utc, cause=cause,
            objective_weights=dict(planner_cfg.weights),
            candidate_window_ids=tuple(w.id for w in candidates), selections=(),
            solver_status=SolverStatus.OPTIMAL, objective_value=0.0, best_bound=0.0,
            runtime_s=perf_counter() - started,
        )
        return plan, {}

    base_time = min(option.start_utc for window in active for option in window.options)
    for window in active:
        vars_for_window = []
        for option in sorted(window.options, key=lambda o: o.option_id):
            variable = model.new_bool_var(f"select_{option.option_id}")
            option_vars[option.option_id] = (variable, window, option)
            vars_for_window.append(variable)
            intervals[window.spacecraft_id].append(
                model.new_optional_fixed_size_interval_var(
                    _microseconds(option.start_utc - base_time),
                    max(1, _microseconds(option.end_utc - option.start_utc)),
                    variable,
                    f"interval_{option.option_id}",
                )
            )
        model.add_at_most_one(vars_for_window)

    for left, right in pair_conflicts:
        if left in option_vars and right in option_vars:
            model.add(option_vars[left][0] + option_vars[right][0] <= 1)
        elif left in option_vars and right in fixed_option_ids:
            variable = option_vars[left][0]
            model.add(variable == 0)
        elif right in option_vars and left in fixed_option_ids:
            model.add(option_vars[right][0] == 0)

    for vars_for_sat in intervals.values():
        model.add_no_overlap(vars_for_sat)

    all_fixed = list(resolve_committed(committed, committed_selections))

    by_source: dict[str, list] = defaultdict(list)
    by_sat_orbit: dict[tuple[str, int], list] = defaultdict(list)
    for variable, window, option in option_vars.values():
        by_source[window.source_id].append(variable)
        by_sat_orbit[(window.spacecraft_id, window.orbit_number)].append((variable, window))
    fixed_by_orbit: dict[tuple[str, int], list[ObservationWindow]] = defaultdict(list)
    for window, _ in all_fixed:
        fixed_by_orbit[(window.spacecraft_id, window.orbit_number)].append(window)
    for source_id, variables in by_source.items():
        model.add(sum(variables) <= planner_cfg.max_visits_per_source_per_solve)

    for key, entries in by_sat_orbit.items():
        profile = spacecraft[key[0]]
        model.add(
            sum(variable for variable, _ in entries) + len(fixed_by_orbit[key])
            <= profile.resources.max_acquisitions_per_orbit
        )
        model.add(
            sum(variable * window.data_bytes for variable, window in entries)
            + sum(w.data_bytes for w in fixed_by_orbit[key])
            <= profile.resources.storage_bytes
        )

    # Per-orbit storage releases at each orbit boundary. Energy is modeled as a time-ordered
    # prefix budget, with configured recharge between orbit numbers and a battery-capacity cap.
    for sat_id, profile in spacecraft.items():
        sat_orbits = sorted(
            {orbit for (sid, orbit) in by_sat_orbit if sid == sat_id}
            | {orbit for sid, orbit in fixed_by_orbit if sid == sat_id}
        )
        if not sat_orbits:
            continue
        first_orbit = sat_orbits[0]
        energy_terms: list[tuple[object | None, float]] = []
        for (sid, _), entries in by_sat_orbit.items():
            if sid == sat_id:
                energy_terms.extend((var, window.energy_wh) for var, window in entries)
        energy_terms.extend((None, window.energy_wh) for window, _ in all_fixed if window.spacecraft_id == sat_id)
        cap_wh = Fraction(str(profile.resources.battery_capacity_wh)) * (
            1 - Fraction(str(profile.resources.min_state_of_charge))
        )
        initial_wh = Fraction(str(profile.resources.battery_capacity_wh)) * max(
            Fraction(), Fraction(str(profile.resources.initial_state_of_charge))
            - Fraction(str(profile.resources.min_state_of_charge))
        )
        recharge_wh = Fraction(str(profile.resources.orbit_average_recharge_wh))
        energy_values = [Fraction(str(value)) for _, value in energy_terms]
        energy_scale = lcm(
            *(value.denominator for value in [*energy_values, cap_wh, initial_wh, recharge_wh])
        )
        energy_ints = [
            value.numerator * (energy_scale // value.denominator) for value in energy_values
        ]
        energy_by_orbit: dict[int, list[tuple[object | None, int]]] = defaultdict(list)
        i = 0
        for (sid, orbit), entries in by_sat_orbit.items():
            if sid == sat_id:
                for var, window in entries:
                    energy_by_orbit[orbit].append((var, energy_ints[i]))
                    i += 1
        for window, _ in all_fixed:
            if window.spacecraft_id == sat_id:
                energy_by_orbit[window.orbit_number].append((None, energy_ints[i]))
                i += 1
        for orbit in sat_orbits:
            accumulated = []
            for prior_orbit in sat_orbits:
                if prior_orbit > orbit:
                    break
                accumulated.extend(energy_by_orbit.get(prior_orbit, ()))
            terms = [var * coefficient for var, coefficient in accumulated if var is not None]
            fixed_energy = sum(coefficient for var, coefficient in accumulated if var is None)
            available = min(cap_wh, initial_wh + max(0, orbit - first_orbit) * recharge_wh)
            bound = available.numerator * (energy_scale // available.denominator)
            model.add(sum(terms) + fixed_energy <= bound)

    ordered_option_ids = sorted(option_vars)
    tie_rank_sum = len(ordered_option_ids) * (len(ordered_option_ids) + 1) // 2
    primary_factor = tie_rank_sum + 1
    primary_coefficients = {
        option_id: utilities[window.id].integer_utility
        for option_id, (_, window, _) in option_vars.items()
    }
    tie_objective_terms = [
        option_vars[option_id][0] * (primary_coefficients[option_id] * primary_factor - rank)
        for rank, option_id in enumerate(ordered_option_ids, start=1)
    ]
    tie_break_enabled = sum(
        max(0, primary_coefficients[option_id] * primary_factor - rank)
        for rank, option_id in enumerate(ordered_option_ids, start=1)
    ) < 2**62
    if tie_break_enabled:
        model.maximize(sum(tie_objective_terms))
    else:
        model.maximize(
            sum(option_vars[option_id][0] * primary_coefficients[option_id]
                for option_id in ordered_option_ids)
        )
    solver = cp_model.CpSolver()
    solver.parameters.random_seed = derive_seed(
        random_seed, "solver", policy_id.value, revision
    )
    solver.parameters.num_search_workers = planner_cfg.solver.num_workers
    solver.parameters.log_search_progress = False
    if planner_cfg.solver.mode == "reproducible":
        solver.parameters.max_deterministic_time = planner_cfg.solver.max_deterministic_time
    else:
        solver.parameters.max_time_in_seconds = planner_cfg.solver.fast_mode_wall_time_seconds
    status_code = solver.solve(model)

    status_map = {
        cp_model.OPTIMAL: SolverStatus.OPTIMAL,
        cp_model.FEASIBLE: SolverStatus.FEASIBLE,
        cp_model.INFEASIBLE: SolverStatus.INFEASIBLE,
        cp_model.MODEL_INVALID: SolverStatus.MODEL_INVALID,
        cp_model.UNKNOWN: SolverStatus.UNKNOWN,
    }
    solver_status = status_map.get(status_code, SolverStatus.UNKNOWN)
    selected = []
    starts: dict[str, datetime] = {}
    objective_value = best_bound = None
    if status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        selected = sorted(
            (option_id for option_id, (var, _, _) in option_vars.items() if solver.boolean_value(var))
        )
        starts = {
            option_vars[option_id][1].id: option_vars[option_id][2].start_utc
            for option_id in selected
        }
        primary_value = sum(primary_coefficients[option_id] for option_id in selected)
        objective_value = primary_value / planner_cfg.utility_integer_scale
        if tie_break_enabled:
            best_bound = (
                solver.best_objective_bound + tie_rank_sum
            ) / primary_factor / planner_cfg.utility_integer_scale
        else:
            best_bound = solver.best_objective_bound / planner_cfg.utility_integer_scale

    plan = Plan(
        run_id=run_id,
        policy_id=policy_id,
        revision=revision,
        created_at_sim_utc=created_at_sim_utc,
        cause=cause,
        objective_weights=dict(planner_cfg.weights),
        candidate_window_ids=tuple(w.id for w in candidates),
        selections=tuple(
            Selection(window_id=option_vars[option_id][1].id, option_id=option_id)
            for option_id in selected
        ),
        solver_status=solver_status,
        objective_value=objective_value,
        best_bound=best_bound,
        runtime_s=perf_counter() - started,
    )
    return plan, starts

