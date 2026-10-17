"""Closed vocabularies shared by every AETHER module. Owned by the integrator lane (L1).

Adding a member is a contract change: open a PR that touches only this file and its tests.
"""

from enum import StrEnum


class ProvenanceClass(StrEnum):
    """Immutable origin of a record (PRD FR-DATA-005). Never reassigned after creation."""

    REAL_OBSERVATION = "REAL_OBSERVATION"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    SIMULATED_OBSERVATION = "SIMULATED_OBSERVATION"
    SIMULATED_GROUND_TRUTH = "SIMULATED_GROUND_TRUTH"


class ObservationOutcome(StrEnum):
    """Result of an acquisition attempt (PRD 5.5). Only the first two carry emission evidence."""

    DETECTION = "DETECTION"
    VALID_NON_DETECTION = "VALID_NON_DETECTION"
    INVALID_ACQUISITION = "INVALID_ACQUISITION"
    NOT_OBSERVED = "NOT_OBSERVED"


class RejectionReason(StrEnum):
    """Why a candidate window is infeasible (PRD FR-ORB-006). A window may carry several."""

    NOT_VISIBLE = "NOT_VISIBLE"
    FOV = "FOV"
    POINTING = "POINTING"
    SLEW = "SLEW"
    DARK = "DARK"
    BLACKOUT = "BLACKOUT"
    POWER = "POWER"
    STORAGE = "STORAGE"
    DOWNLINK = "DOWNLINK"
    STALE_ELEMENTS = "STALE_ELEMENTS"
    SHORT_WINDOW = "SHORT_WINDOW"
    UNKNOWN = "UNKNOWN"


class SolverStatus(StrEnum):
    """CP-SAT status names plus HEURISTIC for greedy baselines that do not call a solver."""

    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    MODEL_INVALID = "MODEL_INVALID"
    UNKNOWN = "UNKNOWN"
    HEURISTIC = "HEURISTIC"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Regime(StrEnum):
    """Emission-persistence regime of a source (Parameter_Register PR-P20)."""

    PERSISTENT = "PERSISTENT"
    INTERMITTENT = "INTERMITTENT"
    EPISODIC = "EPISODIC"


class PolicyId(StrEnum):
    """Scheduling policies (PRD 7.5). GREEDY_EIG is the strong comparator.

    RANDOM_FEASIBLE and ORACLE are REFERENCE policies for the discriminability gate (G4.5), not
    competitors. ORACLE reads truth, so it lives in aether.evaluation, never in aether.planning.
    """

    FIRST_FEASIBLE = "first_feasible"
    LARGEST_FIRST = "largest_first"
    STATIC_PRIORITY = "static_priority"
    ADAPTIVE_EIG = "adaptive_eig"
    GREEDY_EIG = "greedy_eig"
    RANDOM_FEASIBLE = "random_feasible"
    ORACLE = "oracle"


class UncertaintyKind(StrEnum):
    """How a provider expressed flux uncertainty. Never inferred when the provider is silent."""

    STDDEV = "STDDEV"
    INTERVAL = "INTERVAL"
    UNKNOWN = "UNKNOWN"


class MissingReason(StrEnum):
    """Why a nullable scientific value is null (Parameter_2 API-CONV-006)."""

    NOT_PROVIDED = "NOT_PROVIDED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CRITERIA_NOT_MET = "CRITERIA_NOT_MET"  # e.g. EMIT V002 rate 'N/A'
    INVALID_ACQUISITION = "INVALID_ACQUISITION"
    UNKNOWN = "UNKNOWN"


class AcquisitionStatus(StrEnum):
    """Status of a REAL acquisition, independent of plume detection (FR-DATA-006)."""

    VALID = "VALID"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


class EventType(StrEnum):
    """Closed-loop event log types (PRD 10.3)."""

    SCENARIO_CREATED = "SCENARIO_CREATED"
    DATA_READY = "DATA_READY"
    ORBIT_WINDOWS_READY = "ORBIT_WINDOWS_READY"
    BELIEF_INITIALIZED = "BELIEF_INITIALIZED"
    PLAN_REQUESTED = "PLAN_REQUESTED"
    PLAN_PROPOSED = "PLAN_PROPOSED"
    PLAN_VALIDATED = "PLAN_VALIDATED"
    OBSERVATION_WINDOW_EXECUTED = "OBSERVATION_WINDOW_EXECUTED"
    BELIEF_UPDATED = "BELIEF_UPDATED"
    BELIEF_PREDICTED = "BELIEF_PREDICTED"
    FORECAST_REVISED = "FORECAST_REVISED"
    PLAN_REJECTED = "PLAN_REJECTED"
    NOT_OBSERVED = "NOT_OBSERVED"
    REPLAN_REQUESTED = "REPLAN_REQUESTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"
    RUN_CANCELLED = "RUN_CANCELLED"
    EVALUATION_COMPLETED = "EVALUATION_COMPLETED"
