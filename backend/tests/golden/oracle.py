"""Exhaustive schedule oracle for tiny instances (L8).

Kept outside ``aether.planning`` so production scheduling code cannot accidentally depend on the
test oracle. It enumerates every option subset and asks the independent checker to validate it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from aether.config import ScenarioConfig, SensorProfile, SpacecraftProfile
from aether.contracts.enums import PolicyId, SolverStatus
from aether.contracts.models import CandidateUtility, ObservationWindow, Plan, Selection, Source
from aether.planning.checker import check_schedule


@dataclass(frozen=True)
class OracleResult:
    selected_option_ids: tuple[str, ...]
    objective_value: int


def brute_force_optimum(
    windows: Iterable[ObservationWindow],
    utilities: Mapping[str, CandidateUtility],
    sources: Iterable[Source],
    spacecraft: Mapping[str, SpacecraftProfile],
    sensor: SensorProfile,
    scenario: ScenarioConfig,
) -> OracleResult:
    """Return the maximum integer-utility feasible subset for at most 12 candidate windows."""
    candidates = tuple(
        sorted(
            (
                (window, option)
                for window in windows
                if window.feasible
                for option in window.options
            ),
            key=lambda item: item[1].option_id,
        )
    )
    if len(candidates) > 12:
        raise ValueError("brute-force oracle is limited to at most 12 options")
    missing = sorted({window.id for window, _ in candidates if window.id not in utilities})
    if missing:
        raise KeyError(f"missing candidate utilities for windows: {missing}")
    utility_by_option = {
        option.option_id: utilities[window.id].integer_utility for window, option in candidates
    }

    best_ids: tuple[str, ...] = ()
    best_value = 0
    option_ids = tuple(option.option_id for _, option in candidates)
    option_window = {option.option_id: window for window, option in candidates}
    for mask in range(1 << len(candidates)):
        chosen = tuple(option_ids[i] for i in range(len(candidates)) if mask & (1 << i))
        value = sum(utility_by_option[option_id] for option_id in chosen)
        if value < best_value or (value == best_value and chosen >= best_ids):
            continue
        window_by_id = {window.id: window for window, _ in candidates}
        plan = Plan(
            run_id="oracle",
            policy_id=PolicyId.GREEDY_EIG,
            revision=0,
            created_at_sim_utc=scenario.simulation_epoch_utc,
            cause="exhaustive oracle candidate",
            objective_weights={},
            candidate_window_ids=tuple(window_by_id),
            selections=tuple(
                Selection(window_id=option_window[option_id].id, option_id=option_id)
                for option_id in chosen
            ),
            solver_status=SolverStatus.OPTIMAL,
            objective_value=float(value),
            best_bound=float(value),
            runtime_s=0.0,
        )
        validation = check_schedule(
            plan, tuple(window_by_id.values()), sources, spacecraft, sensor, scenario
        )
        if validation.ok:
            best_ids, best_value = chosen, value
    return OracleResult(best_ids, best_value)
