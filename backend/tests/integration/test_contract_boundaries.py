from pathlib import Path

import pytest
from pydantic import ValidationError

from aether.config import load_scenario
from aether.contracts.enums import ProvenanceClass, Regime
from aether.contracts.models import BeliefSnapshot, Plan, RunEvent, revalidate_contract


def _belief():
    return BeliefSnapshot(
        source_id="s0",
        state_time_utc="2025-01-01T00:00:00Z",
        p_active=0.5,
        regime_probs={Regime.EPISODIC: 0.5, Regime.PERSISTENT: 0.5},
        flux_median_kg_h=10,
        flux_ci90_kg_h=(1, 100),
        entropy_bits=0.8,
        model_version="p0-0",
        evidence_ids=(),
        received_new_evidence=False,
    )


def test_nested_contract_mappings_cannot_be_mutated():
    belief = _belief()
    with pytest.raises(TypeError, match="immutable"):
        belief.regime_probs[Regime.EPISODIC] = 1.0


def test_model_copy_provenance_bypass_is_rejected_at_boundary():
    invalid = _belief().model_copy(
        update={"provenance_class": ProvenanceClass.SIMULATED_GROUND_TRUTH}
    )
    with pytest.raises(ValidationError, match="MODEL_INFERENCE"):
        revalidate_contract(invalid)


def test_model_copy_invalid_plan_is_rejected_at_boundary():
    plan = Plan(
        run_id="r",
        policy_id="adaptive_eig",
        revision=0,
        created_at_sim_utc="2025-01-01T00:00:00Z",
        cause="initial",
        objective_weights={"information": 1.0},
        candidate_window_ids=(),
        selections=(),
        solver_status="OPTIMAL",
        objective_value=0,
        best_bound=0,
    )
    invalid = plan.model_copy(update={"revision": -1})
    with pytest.raises(ValidationError):
        revalidate_contract(invalid)


def test_nested_event_payload_is_immutable():
    event = RunEvent(
        event_id="e1",
        run_id="r",
        sequence_number=1,
        event_time_sim_utc="2025-01-01T00:00:00Z",
        event_type="RUN_COMPLETED",
        actor="simulator",
        payload={"nested": {"values": [1, 2]}},
        payload_sha256="0" * 64,
        config_hash="0" * 64,
        model_version="p0-0",
    )
    with pytest.raises(TypeError, match="immutable"):
        event.payload["new"] = "value"
    with pytest.raises(TypeError, match="immutable"):
        event.payload["nested"]["value"] = 3
    assert event.payload["nested"]["values"] == (1, 2)


def test_planner_configuration_mappings_are_immutable():
    config_path = Path(__file__).resolve().parents[3] / "configs" / "demo.yaml"
    cfg = load_scenario(config_path).model
    with pytest.raises(TypeError, match="immutable"):
        cfg.planner.weights["information"] = 0
    with pytest.raises(TypeError, match="immutable"):
        cfg.spacecraft["vsat_a"] = cfg.spacecraft["vsat_b"]
