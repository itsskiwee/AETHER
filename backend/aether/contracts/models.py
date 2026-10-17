"""Canonical data contracts passed between lanes (PRD 11.1). Owned by the integrator lane (L1).

Rules:
- All models are frozen. Create a new object instead of mutating one.
- All datetimes must be timezone-aware UTC. Naive datetimes are rejected.
- Units are in the field names (``_kg_h``, ``_deg``, ``_s``, ``_bytes``, ``_wh``, ``_bits``).
- Geodetic coordinates are WGS84 / EPSG:4326, longitude before latitude.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, computed_field, model_validator

from aether.contracts.enums import (
    AcquisitionStatus,
    EventType,
    MissingReason,
    ObservationOutcome,
    PolicyId,
    ProvenanceClass,
    Regime,
    RejectionReason,
    SolverStatus,
    UncertaintyKind,
)


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("datetime must be timezone-aware UTC")
    return value


UtcDatetime = Annotated[datetime, AfterValidator(_require_utc)]
Probability = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --- Real data -------------------------------------------------------------------------------


class DataSource(Contract):
    provider: str
    dataset: str
    version: str
    url: str
    license_url: str | None
    citation_text: str
    retrieved_at_utc: UtcDatetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PlumeObservation(Contract):
    """A real, provider-published plume. Only the ingestion lane may construct these."""

    id: str
    provenance_class: ProvenanceClass = ProvenanceClass.REAL_OBSERVATION
    provider: str
    native_id: str
    dataset_version: str
    acquisition_time_utc: UtcDatetime
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    geometry_geojson: dict | None
    acquisition_id: str | None  # links to a real Acquisition when the provider supplies one
    emission_rate_kg_h: float | None
    emission_rate_uncertainty_kg_h: float | None
    uncertainty_kind: UncertaintyKind = UncertaintyKind.UNKNOWN  # never inferred
    missing_rate_reason: MissingReason | None
    quality_flags: tuple[str, ...] = ()
    raw_properties: dict
    source: DataSource

    @model_validator(mode="after")
    def _real_only(self) -> PlumeObservation:
        if self.provenance_class is not ProvenanceClass.REAL_OBSERVATION:
            raise ValueError("PlumeObservation must be REAL_OBSERVATION")
        if self.emission_rate_kg_h is None and not self.missing_rate_reason:
            raise ValueError("null emission rate requires missing_rate_reason")
        return self


class Acquisition(Contract):
    """A REAL instrument acquisition, which may exist without any plume (FR-DATA-006).

    Valid non-detections in real data need one of these with known footprint and status. They are
    never inferred from the absence of plume rows.
    """

    id: str
    provenance_class: ProvenanceClass = ProvenanceClass.REAL_OBSERVATION
    platform: str
    sensor: str
    start_utc: UtcDatetime
    end_utc: UtcDatetime
    coverage_geojson: dict | None
    status: AcquisitionStatus
    quality_flags: tuple[str, ...] = ()
    source: DataSource

    @model_validator(mode="after")
    def _real_only(self) -> Acquisition:
        if self.provenance_class is not ProvenanceClass.REAL_OBSERVATION:
            raise ValueError("Acquisition must be REAL_OBSERVATION")
        return self


# --- Scenario entities -----------------------------------------------------------------------


class Source(Contract):
    """A source hypothesis (not a facility). Synthetic sources may be placed at real plume sites."""

    id: str
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    seeded_from_plume_id: str | None = None
    attribution_status: str = "UNATTRIBUTED"


def _check_unit(v: tuple[float, float, float]) -> None:
    norm = sum(c * c for c in v) ** 0.5
    if abs(norm - 1.0) > 1e-6:
        raise ValueError(f"line-of-sight vector must be unit length, got |v|={norm}")


class AcquisitionOption(Contract):
    """One discrete acquisition start time inside a window (PRD 20: discretized start times).

    The solver selects options, not windows, so slew between two options is computed from the
    line of sight at the actual times. Identity is derived from its window and exact start time.
    """

    option_id: str
    window_id: str
    start_utc: UtcDatetime
    end_utc: UtcDatetime  # start + sensor exposure
    off_nadir_deg: float
    sun_elevation_deg: float
    los_unit_ecef: tuple[float, float, float]

    @model_validator(mode="after")
    def _consistent(self) -> AcquisitionOption:
        if self.option_id != acquisition_option_id(self.window_id, self.start_utc):
            raise ValueError("option_id must be derived from window_id and start_utc")
        if self.end_utc <= self.start_utc:
            raise ValueError("end_utc must be after start_utc")
        _check_unit(self.los_unit_ecef)
        return self


def acquisition_option_id(window_id: str, start_utc: datetime) -> str:
    """Build a stable option ID from its window and UTC start time, never its list position."""
    stamp = start_utc.strftime("%Y%m%dT%H%M%S")
    if start_utc.microsecond:
        stamp += f".{start_utc.microsecond:06d}"
    return f"{window_id}@{stamp}Z"


class ObservationWindow(Contract):
    """One spacecraft/sensor/source access interval, feasible or rejected.

    ``feasible`` is geometry and hard rules only. Success probability lives in ``p_valid_forecast``
    on CandidateUtility and must never be folded into feasibility. Feasible windows carry at least
    one AcquisitionOption; rejected windows carry none.
    """

    id: str
    spacecraft_id: str
    sensor_id: str
    source_id: str
    start_utc: UtcDatetime
    end_utc: UtcDatetime
    pass_id: str  # groups windows of one regional overflight; replanning happens per pass
    orbit_number: int
    feasible: bool
    rejection_reasons: tuple[RejectionReason, ...] = ()
    min_off_nadir_deg: float
    options: tuple[AcquisitionOption, ...] = ()
    duration_s: float  # sensor exposure per acquisition
    energy_wh: float
    data_bytes: int

    @model_validator(mode="after")
    def _consistent(self) -> ObservationWindow:
        if self.end_utc <= self.start_utc:
            raise ValueError("end_utc must be after start_utc")
        if self.feasible == bool(self.rejection_reasons):
            raise ValueError("feasible windows have no rejection reasons; rejected ones need one")
        if self.feasible != bool(self.options):
            raise ValueError("feasible windows need >= 1 option; rejected windows have none")
        option_ids = [option.option_id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("window acquisition option IDs must be unique")
        for opt in self.options:
            if opt.window_id != self.id:
                raise ValueError("option belongs to a different window")
            if opt.start_utc < self.start_utc or opt.end_utc > self.end_utc:
                raise ValueError("option lies outside its window")
        return self


class CandidateUtility(Contract):
    """Objective components computed BEFORE the solve (PRD FR-OPT-001)."""

    window_id: str
    plan_revision: int
    expected_info_gain_bits: float
    decision_relevance: float
    latency_s: float
    resource_cost: float
    p_valid_forecast: Probability
    utility: float
    integer_utility: int


class Selection(Contract):
    window_id: str
    option_id: str


class Plan(Contract):
    run_id: str
    policy_id: PolicyId
    revision: int
    created_at_sim_utc: UtcDatetime
    cause: str
    objective_weights: dict[str, float]
    candidate_window_ids: tuple[str, ...]
    selections: tuple[Selection, ...]
    solver_status: SolverStatus
    objective_value: float | None
    best_bound: float | None
    runtime_s: float
    validation_ok: bool | None = None  # set by the independent checker, never by the solver

    @model_validator(mode="after")
    def _unique_selected_windows(self) -> Plan:
        window_ids = [selection.window_id for selection in self.selections]
        if len(window_ids) != len(set(window_ids)):
            raise ValueError("a Plan may select at most one option per window")
        return self

    @computed_field
    @property
    def selected_window_ids(self) -> tuple[str, ...]:
        return tuple(selection.window_id for selection in self.selections)


class ScheduleViolation(Contract):
    option_ids: tuple[str, ...]
    rule: str  # e.g. "NO_OVERLAP", "SLEW", "STORAGE", "ENERGY", "SOURCE_LIMIT", "INFEASIBLE_WINDOW"
    detail: str


class ScheduleValidation(Contract):
    plan_revision: int
    ok: bool
    violations: tuple[ScheduleViolation, ...]
    checker_version: str


# --- Simulation and inference ----------------------------------------------------------------


class SimulatedAcquisition(Contract):
    """What the planner side learns from one simulated acquisition. Contains NO truth.

    ``wind_estimate_m_s`` is an analysis-style estimate (truth plus PR-W13 error), never the true
    wind. ``scene_cloud_fraction`` is observable from the scene itself, so it may be reported.
    """

    id: str
    option_id: str
    window_id: str
    source_id: str
    spacecraft_id: str
    sensor_id: str
    time_utc: UtcDatetime
    provenance_class: ProvenanceClass = ProvenanceClass.SIMULATED_OBSERVATION
    outcome: ObservationOutcome
    measured_flux_kg_h: float | None
    off_nadir_deg: float
    wind_estimate_m_s: float = Field(gt=0)
    scene_cloud_fraction: Probability
    rng_key: str

    @model_validator(mode="after")
    def _simulated_only(self) -> SimulatedAcquisition:
        if self.provenance_class is not ProvenanceClass.SIMULATED_OBSERVATION:
            raise ValueError("SimulatedAcquisition must be SIMULATED_OBSERVATION")
        if self.outcome is not ObservationOutcome.DETECTION and self.measured_flux_kg_h is not None:
            raise ValueError("only detections carry a measured flux")
        return self


class BeliefSnapshot(Contract):
    source_id: str
    state_time_utc: UtcDatetime
    provenance_class: ProvenanceClass = ProvenanceClass.MODEL_INFERENCE
    p_active: Probability
    regime_probs: dict[Regime, Probability]
    flux_median_kg_h: float
    flux_ci90_kg_h: tuple[float, float]
    entropy_bits: float = Field(ge=0, le=1)
    model_version: str
    evidence_ids: tuple[str, ...]
    received_new_evidence: bool  # False for pure time-propagation (PRD 5.6 persistence test)

    @model_validator(mode="after")
    def _coherent(self) -> BeliefSnapshot:
        if self.provenance_class is not ProvenanceClass.MODEL_INFERENCE:
            raise ValueError("BeliefSnapshot must be MODEL_INFERENCE")
        if abs(sum(self.regime_probs.values()) - 1.0) > 1e-9:
            raise ValueError("regime_probs must sum to 1")
        lo, hi = self.flux_ci90_kg_h
        if not 0 < lo <= self.flux_median_kg_h <= hi:
            raise ValueError("require 0 < ci90_low <= median <= ci90_high")
        return self


class RunEvent(Contract):
    event_id: str
    run_id: str
    sequence_number: int
    event_time_sim_utc: UtcDatetime
    event_type: EventType
    actor: str
    payload: dict
    payload_sha256: str
    config_hash: str
    model_version: str


class RunRecord(Contract):
    """Everything one policy run produced. Serialized to runs/<run_id>/run.json for the UI/API.

    Contains NO hidden truth. Truth is scored separately by aether.evaluation.
    """

    run_id: str
    policy_id: PolicyId
    scenario_id: str
    family: str
    seed: int
    model_config_hash: str
    truth_config_hash: str
    code_version: str
    sources: tuple[Source, ...]
    windows: tuple[ObservationWindow, ...]
    plans: tuple[Plan, ...]
    validations: tuple[ScheduleValidation, ...]
    utilities: tuple[CandidateUtility, ...]
    acquisitions: tuple[SimulatedAcquisition, ...]
    beliefs: tuple[BeliefSnapshot, ...]  # at every evaluation time and after every update
    events: tuple[RunEvent, ...]
