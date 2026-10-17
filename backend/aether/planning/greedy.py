"""Shared feasibility and insertion logic for deterministic greedy policies."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from fractions import Fraction
from typing import Iterable

from aether.config import PlannerConfig, SpacecraftProfile
from aether.contracts.models import (
    AcquisitionOption,
    CandidateUtility,
    ObservationWindow,
    Plan,
    Selection,
)
from aether.orbit import slew_time_s


def resolve_committed(
    windows: Iterable[ObservationWindow], selections: Iterable[Selection]
) -> tuple[tuple[ObservationWindow, AcquisitionOption], ...]:
    windows = tuple(windows)
    selections = tuple(selections)
    by_window = {window.id: window for window in windows}
    if len(by_window) != len(windows):
        raise ValueError("committed window IDs must be unique")
    if len({selection.window_id for selection in selections}) != len(selections):
        raise ValueError("committed selections must contain at most one option per window")
    if set(by_window) != {selection.window_id for selection in selections}:
        raise ValueError("every committed window must have exactly one explicit selection")
    resolved = []
    for selection in selections:
        window = by_window[selection.window_id]
        option = next(
            (item for item in window.options if item.option_id == selection.option_id), None
        )
        if option is None:
            raise ValueError(
                f"committed option {selection.option_id!r} does not belong to window "
                f"{selection.window_id!r}"
            )
        resolved.append((window, option))
    return tuple(resolved)


def conflict_pairs(
    windows: Iterable[ObservationWindow],
    spacecraft: dict[str, SpacecraftProfile],
    committed: Iterable[ObservationWindow] = (),
    committed_selections: Iterable[Selection] = (),
) -> tuple[tuple[str, str], ...]:
    """Option ID pairs that cannot both be scheduled; also validates fixed acquisitions."""
    windows = tuple(windows)
    fixed = resolve_committed(committed, committed_selections)
    options = [(w, o) for w in windows for o in w.options]
    pairs: set[tuple[str, str]] = set()
    for i, (wi, oi) in enumerate(options):
        profile = spacecraft[wi.spacecraft_id]
        for wj, oj in options[i + 1 :]:
            if wi.id == wj.id or wi.spacecraft_id != wj.spacecraft_id:
                continue
            if not _can_sequence(wi, oi, wj, oj, profile):
                pairs.add(tuple(sorted((oi.option_id, oj.option_id))))
        for wc, oc in fixed:
            if wi.spacecraft_id == wc.spacecraft_id and not _can_sequence(
                wi, oi, wc, oc, profile
            ):
                pairs.add(tuple(sorted((oi.option_id, oc.option_id))))
    for i, (wi, oi) in enumerate(fixed):
        profile = spacecraft[wi.spacecraft_id]
        for wj, oj in fixed[i + 1 :]:
            if wi.spacecraft_id == wj.spacecraft_id and not _can_sequence(
                wi, oi, wj, oj, profile
            ):
                raise ValueError(f"committed acquisitions conflict: {wi.id}, {wj.id}")
    return tuple(sorted(pairs))


def _can_sequence(
    wi: ObservationWindow,
    oi: AcquisitionOption,
    wj: ObservationWindow,
    oj: AcquisitionOption,
    profile: SpacecraftProfile,
) -> bool:
    if oi.end_utc <= oj.start_utc:
        return (oj.start_utc - oi.end_utc).total_seconds() >= slew_time_s(
            oi, oj, profile.attitude
        )
    if oj.end_utc <= oi.start_utc:
        return (oi.start_utc - oj.end_utc).total_seconds() >= slew_time_s(
            oj, oi, profile.attitude
        )
    return False


def _fraction(value: float) -> Fraction:
    return Fraction(str(value))


def can_add(
    window: ObservationWindow,
    option: AcquisitionOption,
    selected: list[tuple[ObservationWindow, AcquisitionOption]],
    spacecraft: dict[str, SpacecraftProfile],
    planner_cfg: PlannerConfig,
    committed: tuple[ObservationWindow, ...],
    committed_selections: tuple[Selection, ...],
) -> bool:
    """Return whether adding one option preserves the same hard limits as CP-SAT."""
    same = [(w, o) for w, o in selected if w.spacecraft_id == window.spacecraft_id]
    fixed = [(w, o) for w, o in resolve_committed(committed, committed_selections)
             if w.spacecraft_id == window.spacecraft_id]
    profile = spacecraft[window.spacecraft_id]
    if any(not _can_sequence(window, option, w, o, profile) for w, o in (*same, *fixed)):
        return False

    all_acquisitions = [*selected, (window, option)]
    if (
        sum(w.source_id == window.source_id for w, _ in all_acquisitions)
        > planner_cfg.max_visits_per_source_per_solve
    ):
        return False
    orbit_items = [(w, o) for w, o in all_acquisitions if w.spacecraft_id == window.spacecraft_id]
    same_orbit = [(w, o) for w, o in orbit_items if w.orbit_number == window.orbit_number]
    if len(same_orbit) > profile.resources.max_acquisitions_per_orbit:
        return False
    if sum(w.data_bytes for w, _ in same_orbit) > profile.resources.storage_bytes:
        return False

    orbit_numbers = sorted({w.orbit_number for w, _ in orbit_items})
    start_orbit = orbit_numbers[0] if orbit_numbers else window.orbit_number
    prefix = [(w, o) for w, o in orbit_items if w.orbit_number <= window.orbit_number]
    used = sum((_fraction(w.energy_wh) for w, _ in prefix), Fraction())
    initial_wh = _fraction(profile.resources.battery_capacity_wh) * max(
        Fraction(), _fraction(profile.resources.initial_state_of_charge)
        - _fraction(profile.resources.min_state_of_charge)
    )
    recharge = _fraction(profile.resources.orbit_average_recharge_wh)
    available = min(
        _fraction(profile.resources.battery_capacity_wh)
        * (1 - _fraction(profile.resources.min_state_of_charge)),
        initial_wh + (window.orbit_number - start_orbit) * recharge,
    )
    return used <= available


def greedy_insert(
    windows: tuple[ObservationWindow, ...] | list[ObservationWindow],
    order: Iterable[str],
    utilities: dict[str, CandidateUtility],
    spacecraft: dict[str, SpacecraftProfile],
    planner_cfg: PlannerConfig,
    committed: tuple[ObservationWindow, ...] | list[ObservationWindow],
    committed_selections: tuple[Selection, ...] | list[Selection] = (),
) -> tuple[tuple[Selection, ...], dict[str, datetime]]:
    """Try windows in the supplied order, choosing the earliest feasible option per window."""
    by_id = {window.id: window for window in windows if window.feasible}
    committed = tuple(committed)
    selected: list[tuple[ObservationWindow, AcquisitionOption]] = []
    selected_windows: set[str] = set()
    for window_id in order:
        window = by_id.get(window_id)
        if window is None or window_id in selected_windows:
            continue
        utility = utilities.get(window_id)
        if utility is None or utility.expected_info_gain_bits < planner_cfg.min_utility_bits:
            continue
        for option in sorted(window.options, key=lambda item: (item.start_utc, item.option_id)):
            if can_add(
                window, option, selected, spacecraft, planner_cfg,
                committed, tuple(committed_selections),
            ):
                selected.append((window, option))
                selected_windows.add(window_id)
                break
    selected.sort(key=lambda item: (item[1].start_utc, item[1].option_id))
    return tuple(Selection(window_id=w.id, option_id=o.option_id) for w, o in selected), {
        window.id: option.start_utc for window, option in selected
    }


def build_heuristic_plan(
    *,
    run_id: str,
    policy_id,
    revision: int,
    created_at_sim_utc: datetime,
    cause: str,
    planner_cfg: PlannerConfig,
    windows: Iterable[ObservationWindow],
    selections: tuple[Selection, ...],
) -> Plan:
    return Plan(
        run_id=run_id,
        policy_id=policy_id,
        revision=revision,
        created_at_sim_utc=created_at_sim_utc,
        cause=cause,
        objective_weights=dict(planner_cfg.weights),
        candidate_window_ids=tuple(sorted(w.id for w in windows if w.feasible)),
        selections=selections,
        solver_status="HEURISTIC",
        objective_value=None,
        best_bound=None,
        runtime_s=0.0,
    )


def rejection_reasons(
    windows: Iterable[ObservationWindow],
    selections: Iterable[Selection],
    utilities: dict[str, CandidateUtility],
    planner_cfg: PlannerConfig,
    spacecraft: dict[str, SpacecraftProfile] | None = None,
    committed: Iterable[ObservationWindow] = (),
    committed_selections: Iterable[Selection] = (),
) -> dict[str, str]:
    """Explain each unselected candidate using the planner's closed explanation vocabulary."""
    windows = tuple(windows)
    selections = tuple(selections)
    committed = tuple(committed)
    committed_selections = tuple(committed_selections)
    window_map = {window.id: window for window in windows}
    selected_windows = {selection.window_id for selection in selections}
    chosen = []
    for selection in selections:
        window = window_map.get(selection.window_id)
        if window is None:
            continue
        option = next((o for o in window.options if o.option_id == selection.option_id), None)
        if option is not None:
            chosen.append((window, option))
    fixed = resolve_committed(committed, committed_selections)
    selected_sources = [w.source_id for w, _ in chosen]
    reasons: dict[str, str] = {}
    for window in windows:
        if window.id in selected_windows:
            continue
        if not window.feasible:
            reason = "INFEASIBLE"
        elif window.id not in utilities or utilities[window.id].expected_info_gain_bits < planner_cfg.min_utility_bits:
            reason = "LOW_GAIN"
        elif selected_sources.count(window.source_id) >= planner_cfg.max_visits_per_source_per_solve:
            reason = "SOURCE_LIMIT"
        elif spacecraft is not None and _budget_limited(
            window, chosen, committed, tuple(committed_selections), spacecraft
        ):
            reason = "BUDGET"
        else:
            reason = "CONFLICT"
        reasons[window.id] = reason
    return reasons


def _budget_limited(
    candidate: ObservationWindow,
    chosen: list[tuple[ObservationWindow, AcquisitionOption]],
    committed: tuple[ObservationWindow, ...],
    committed_selections: tuple[Selection, ...],
    spacecraft: dict[str, SpacecraftProfile],
) -> bool:
    profile = spacecraft[candidate.spacecraft_id]
    fixed = [
        (w, o) for w, o in resolve_committed(committed, committed_selections)
        if w.spacecraft_id == candidate.spacecraft_id
    ]
    all_items = [
        *(item for item in chosen if item[0].spacecraft_id == candidate.spacecraft_id),
        *fixed,
    ]
    all_items.append((candidate, candidate.options[0]))
    same_orbit = [w for w, _ in all_items if w.orbit_number == candidate.orbit_number]
    if len(same_orbit) > profile.resources.max_acquisitions_per_orbit:
        return True
    if sum(w.data_bytes for w in same_orbit) > profile.resources.storage_bytes:
        return True
    first_orbit = min(w.orbit_number for w, _ in all_items)
    prefix = [w for w, _ in all_items if w.orbit_number <= candidate.orbit_number]
    used = sum((_fraction(w.energy_wh) for w in prefix), Fraction())
    capacity = _fraction(profile.resources.battery_capacity_wh)
    minimum = _fraction(profile.resources.min_state_of_charge)
    initial = capacity * max(Fraction(), _fraction(profile.resources.initial_state_of_charge) - minimum)
    available = min(
        capacity * (1 - minimum),
        initial
        + (candidate.orbit_number - first_orbit)
        * _fraction(profile.resources.orbit_average_recharge_wh),
    )
    return used > available

