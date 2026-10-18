"""Shared feasibility and insertion logic for deterministic greedy policies."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from fractions import Fraction

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
            if wi.spacecraft_id == wc.spacecraft_id and not _can_sequence(wi, oi, wc, oc, profile):
                pairs.add(tuple(sorted((oi.option_id, oc.option_id))))
    for i, (wi, oi) in enumerate(fixed):
        profile = spacecraft[wi.spacecraft_id]
        for wj, oj in fixed[i + 1 :]:
            if wi.spacecraft_id == wj.spacecraft_id and not _can_sequence(wi, oi, wj, oj, profile):
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
        return (oj.start_utc - oi.end_utc).total_seconds() >= slew_time_s(oi, oj, profile.attitude)
    if oj.end_utc <= oi.start_utc:
        return (oi.start_utc - oj.end_utc).total_seconds() >= slew_time_s(oj, oi, profile.attitude)
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
    now_utc: datetime | None = None,
) -> bool:
    """Return whether adding one option preserves the same hard limits as CP-SAT."""
    same = [(w, o) for w, o in selected if w.spacecraft_id == window.spacecraft_id]
    fixed = resolve_committed(committed, committed_selections)
    profile = spacecraft[window.spacecraft_id]
    if any(
        w.spacecraft_id == window.spacecraft_id and not _can_sequence(window, option, w, o, profile)
        for w, o in (*same, *fixed)
    ):
        return False
    if not _source_limit_ok(window, selected, fixed, planner_cfg, now_utc):
        return False
    return _resource_limits_ok(window, option, selected, fixed, spacecraft)


def _source_limit_ok(
    candidate: ObservationWindow,
    selected: list[tuple[ObservationWindow, AcquisitionOption]],
    fixed: tuple[tuple[ObservationWindow, AcquisitionOption], ...],
    planner_cfg: PlannerConfig,
    now_utc: datetime | None = None,
) -> bool:
    visits = 1 + sum(w.source_id == candidate.source_id for w, _ in selected)
    # PR-O03 is a per-solve cap: completed acquisitions retain resource/temporal
    # effects, but no longer double-count this solve's information gain.
    visits += sum(
        w.source_id == candidate.source_id and (now_utc is None or o.end_utc > now_utc)
        for w, o in fixed
    )
    return visits <= planner_cfg.max_visits_per_source_per_solve


def _resource_limits_ok(
    candidate: ObservationWindow,
    option: AcquisitionOption,
    selected: list[tuple[ObservationWindow, AcquisitionOption]],
    fixed: tuple[tuple[ObservationWindow, AcquisitionOption], ...],
    spacecraft: dict[str, SpacecraftProfile],
) -> bool:
    profile = spacecraft[candidate.spacecraft_id]
    acquisitions = [
        (window, item)
        for window, item in (*selected, *fixed)
        if window.spacecraft_id == candidate.spacecraft_id
    ]
    acquisitions.append((candidate, option))
    by_orbit: dict[int, list[ObservationWindow]] = defaultdict(list)
    for window, _ in acquisitions:
        by_orbit[window.orbit_number].append(window)

    resources = profile.resources
    for orbit_windows in by_orbit.values():
        if len(orbit_windows) > resources.max_acquisitions_per_orbit:
            return False
        if sum(window.data_bytes for window in orbit_windows) > resources.storage_bytes:
            return False

    capacity_wh = _fraction(resources.battery_capacity_wh)
    minimum_soc = _fraction(resources.min_state_of_charge)
    available_wh = max(
        Fraction(),
        capacity_wh * (_fraction(resources.initial_state_of_charge) - minimum_soc),
    )
    max_usable_wh = capacity_wh * (1 - minimum_soc)
    recharge_wh = _fraction(resources.orbit_average_recharge_wh)
    previous_orbit = None
    for orbit in sorted(by_orbit):
        if previous_orbit is not None:
            available_wh = min(
                max_usable_wh,
                available_wh + (orbit - previous_orbit) * recharge_wh,
            )
        energy_used_wh = sum(
            (_fraction(window.energy_wh) for window in by_orbit[orbit]), Fraction()
        )
        if energy_used_wh > available_wh:
            return False
        available_wh -= energy_used_wh
        previous_orbit = orbit
    return True


def greedy_insert(
    windows: tuple[ObservationWindow, ...] | list[ObservationWindow],
    order: Iterable[str],
    utilities: dict[str, CandidateUtility],
    spacecraft: dict[str, SpacecraftProfile],
    planner_cfg: PlannerConfig,
    committed: tuple[ObservationWindow, ...] | list[ObservationWindow],
    committed_selections: tuple[Selection, ...] | list[Selection] = (),
    now_utc: datetime | None = None,
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
        if (
            utility is None
            or utility.expected_info_gain_bits < planner_cfg.min_utility_bits
            or utility.integer_utility <= 0
        ):
            continue
        for option in sorted(window.options, key=lambda item: (item.start_utc, item.option_id)):
            if can_add(
                window,
                option,
                selected,
                spacecraft,
                planner_cfg,
                committed,
                tuple(committed_selections),
                now_utc,
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
        runtime_s=None,
    )


def rejection_reasons(
    windows: Iterable[ObservationWindow],
    selections: Iterable[Selection],
    utilities: dict[str, CandidateUtility],
    planner_cfg: PlannerConfig,
    spacecraft: dict[str, SpacecraftProfile] | None = None,
    committed: Iterable[ObservationWindow] = (),
    committed_selections: Iterable[Selection] = (),
    now_utc: datetime | None = None,
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
    reasons: dict[str, str] = {}
    for window in windows:
        if window.id in selected_windows:
            continue
        if not window.feasible:
            reason = "INFEASIBLE"
        elif (
            window.id not in utilities
            or utilities[window.id].expected_info_gain_bits < planner_cfg.min_utility_bits
            or utilities[window.id].integer_utility <= 0
        ):
            reason = "LOW_GAIN"
        else:
            option_reasons = []
            if spacecraft is None:
                option_reasons = ["NOT_SELECTED"] * len(window.options)
            else:
                profile = spacecraft[window.spacecraft_id]
                for option in window.options:
                    temporal_conflict = any(
                        other_window.spacecraft_id == window.spacecraft_id
                        and not _can_sequence(window, option, other_window, other_option, profile)
                        for other_window, other_option in (*chosen, *fixed)
                    )
                    if temporal_conflict:
                        option_reasons.append("CONFLICT")
                    elif not _source_limit_ok(window, chosen, fixed, planner_cfg, now_utc):
                        option_reasons.append("SOURCE_LIMIT")
                    elif not _resource_limits_ok(window, option, chosen, fixed, spacecraft):
                        option_reasons.append("BUDGET")
                    else:
                        option_reasons.append("NOT_SELECTED")
            reason = (
                option_reasons[0]
                if option_reasons and len(set(option_reasons)) == 1
                else "NOT_SELECTED"
            )
        reasons[window.id] = reason
    return reasons
