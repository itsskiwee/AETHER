"""Planner-visible state handed to every policy. Contains no truth by construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aether.config import ScenarioConfig
from aether.contracts.models import CandidateUtility, ObservationWindow, Selection


@dataclass(frozen=True)
class PlanningContext:
    run_id: str
    revision: int
    now_utc: datetime
    cause: str
    cfg: ScenarioConfig  # bundle.model only, never bundle.truth
    windows: tuple[ObservationWindow, ...]  # feasible, inside [now, now + lookahead], not frozen
    committed: tuple[ObservationWindow, ...]  # already executed or frozen; constrain slew/resources
    utilities: dict[str, CandidateUtility]  # by window_id, computed by the runner from beliefs
    posterior_mean_flux_kg_h: dict[str, float]  # by source_id; for largest_first
    p_active_by_source: dict[str, float]  # by source_id; predicted P(active) at now_utc
    committed_selections: tuple[Selection, ...] = ()  # selected options in committed windows
