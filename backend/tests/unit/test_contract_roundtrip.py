"""Every persisted contract must accept its own public JSON representation."""

import inspect
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from aether.contracts import models

T0 = datetime(2026, 10, 17, tzinfo=UTC)
OPTION_ID = models.acquisition_option_id("w1", T0)


def contract_examples():
    source_data = models.DataSource(
        provider="fixture",
        dataset="fixture",
        version="1",
        url="https://example.com/data",
        license_url=None,
        citation_text="Test fixture",
        retrieved_at_utc=T0,
        sha256="0" * 64,
    )
    source = models.Source(id="s1", lon=0, lat=0)
    timing = models.PlanTiming(
        revision=0,
        checker_retry=0,
        candidate_window_count=1,
        solver_status="OPTIMAL",
        policy_plan_wall_s=0.01,
    )
    dataset_ref = models.InputDatasetRef(
        dataset_id="dataset",
        manifest_path="data/manifests/example.json",
        manifest_sha256="1" * 64,
        normalized_sha256="2" * 64,
        record_count=3,
        in_region_count=2,
        seeded_source_count=0,
        uniform_fill_count=1,
    )
    option = models.AcquisitionOption(
        option_id=OPTION_ID,
        window_id="w1",
        start_utc=T0,
        end_utc=T0 + timedelta(seconds=3),
        off_nadir_deg=0,
        sun_elevation_deg=40,
        los_unit_ecef=(1, 0, 0),
    )
    window = models.ObservationWindow(
        id="w1",
        spacecraft_id="sat",
        sensor_id="sensor",
        source_id="s1",
        start_utc=T0,
        end_utc=T0 + timedelta(seconds=3),
        pass_id="pass",
        orbit_number=1,
        feasible=True,
        min_off_nadir_deg=0,
        options=(option,),
        duration_s=3,
        energy_wh=1,
        data_bytes=1,
    )
    utility = models.CandidateUtility(
        window_id="w1",
        plan_revision=1,
        expected_info_gain_bits=0.1,
        decision_relevance=1,
        latency_s=0,
        resource_cost=1,
        p_valid_forecast=0.8,
        utility=0.1,
        integer_utility=1,
    )
    selection = models.Selection(window_id="w1", option_id=OPTION_ID)
    plan = models.Plan(
        run_id="run",
        policy_id="greedy_eig",
        revision=1,
        created_at_sim_utc=T0,
        cause="test",
        objective_weights={"information": 1},
        candidate_window_ids=("w1",),
        selections=(selection,),
        solver_status="HEURISTIC",
        objective_value=0.1,
        best_bound=None,
        runtime_s=0,
    )
    violation = models.ScheduleViolation(option_ids=(OPTION_ID,), rule="SLEW", detail="fixture")
    validation = models.ScheduleValidation(
        plan_revision=1,
        ok=False,
        violations=(violation,),
        checker_version="test",
    )
    acquisition = models.SimulatedAcquisition(
        id="sim",
        option_id=OPTION_ID,
        window_id="w1",
        source_id="s1",
        spacecraft_id="sat",
        sensor_id="sensor",
        time_utc=T0,
        outcome="DETECTION",
        measured_flux_kg_h=100,
        off_nadir_deg=0,
        wind_estimate_m_s=3,
        scene_cloud_fraction=0.1,
        rng_key="test",
    )
    belief = models.BeliefSnapshot(
        source_id="s1",
        state_time_utc=T0,
        p_active=0.5,
        regime_probs={"PERSISTENT": 0.2, "INTERMITTENT": 0.5, "EPISODIC": 0.3},
        flux_median_kg_h=100,
        flux_ci90_kg_h=(50, 200),
        entropy_bits=1,
        model_version="test",
        evidence_ids=("sim",),
        received_new_evidence=True,
    )
    event = models.RunEvent(
        event_id="event",
        run_id="run",
        sequence_number=1,
        event_time_sim_utc=T0,
        event_type="PLAN_PROPOSED",
        actor="test",
        payload={"plan": plan.model_dump(mode="json")},
        payload_sha256="0" * 64,
        config_hash="0" * 64,
        model_version="test",
    )
    return [
        source_data,
        models.PlumeObservation(
            id="plume",
            provider="fixture",
            native_id="native",
            dataset_version="1",
            acquisition_time_utc=T0,
            lon=0,
            lat=0,
            geometry_geojson=None,
            acquisition_id=None,
            emission_rate_kg_h=None,
            emission_rate_uncertainty_kg_h=None,
            missing_rate_reason="NOT_PROVIDED",
            raw_properties={},
            source=source_data,
        ),
        models.Acquisition(
            id="real",
            platform="fixture",
            sensor="fixture",
            start_utc=T0,
            end_utc=T0 + timedelta(seconds=3),
            coverage_geojson=None,
            status="VALID",
            source=source_data,
        ),
        source,
        option,
        window,
        utility,
        selection,
        plan,
        violation,
        validation,
        acquisition,
        belief,
        event,
        models.RunRecord(
            run_id="run",
            policy_id="greedy_eig",
            scenario_id="scenario",
            family="test",
            seed=1,
            model_config_hash="0" * 64,
            truth_config_hash="0" * 64,
            code_version="test",
            sources=(source,),
            windows=(window,),
            plans=(plan,),
            validations=(validation,),
            utilities=(utility,),
            acquisitions=(acquisition,),
            beliefs=(belief,),
            events=(event,),
            input_dataset=dataset_ref,
        ),
        dataset_ref,
        timing,
        models.RunPerformance(
            run_id="run",
            machine={"python": "3.14"},
            total_run_wall_s=2.0,
            windows_wall_s=1.5,
            windows_from_process_cache=False,
            plan_timings=(timing,),
        ),
    ]


EXAMPLES = contract_examples()
PLAN = next(example for example in EXAMPLES if isinstance(example, models.Plan))


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: type(example).__name__)
def test_contract_json_roundtrip(example):
    assert type(example).model_validate_json(example.model_dump_json()) == example


def test_roundtrip_examples_cover_every_contract_model():
    contract_types = {
        cls
        for _, cls in inspect.getmembers(models, inspect.isclass)
        if issubclass(cls, models.Contract) and cls is not models.Contract
    }
    assert {type(example) for example in EXAMPLES} == contract_types


@pytest.mark.parametrize("selections", [(), PLAN.selections])
def test_plan_roundtrip_preserves_public_selected_window_ids(selections):
    plan = PLAN.model_copy(update={"selections": selections})
    payload = json.loads(plan.model_dump_json())
    assert payload["selected_window_ids"] == [s.window_id for s in selections]
    assert models.Plan.model_validate_json(json.dumps(payload)) == plan


@pytest.mark.parametrize("window_ids", [[], ["other"], ["w1", "w1"], None, "w1"])
def test_plan_rejects_inconsistent_selected_window_ids(window_ids):
    payload = PLAN.model_dump(mode="json")
    payload["selected_window_ids"] = window_ids
    with pytest.raises(ValidationError, match="selected_window_ids must match selections"):
        models.Plan.model_validate_json(json.dumps(payload))


def test_plan_accepts_input_without_computed_field_and_preserves_input():
    payload = PLAN.model_dump()
    original = payload.copy()
    assert models.Plan.model_validate(payload) == PLAN
    assert payload == original
    payload.pop("selected_window_ids")
    assert models.Plan.model_validate(payload) == PLAN


def test_plan_still_rejects_unknown_fields():
    payload = PLAN.model_dump(mode="json")
    payload["unknown"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        models.Plan.model_validate(payload)


def test_planning_context_import_and_default_field_order():
    from dataclasses import fields

    from aether.planning.context import PlanningContext

    names = [field.name for field in fields(PlanningContext)]
    assert names.index("p_active_by_source") < names.index("committed_selections")


def test_plan_rejects_reordered_selected_window_ids():
    payload = PLAN.model_dump(mode="json")
    payload["selections"].append({"window_id": "w2", "option_id": "other"})
    payload["selected_window_ids"] = ["w2", "w1"]
    with pytest.raises(ValidationError, match="selected_window_ids must match selections"):
        models.Plan.model_validate(payload)


def test_plan_still_rejects_multiple_options_for_one_window():
    payload = PLAN.model_dump(mode="json", exclude={"selected_window_ids"})
    payload["selections"].append({"window_id": "w1", "option_id": "other"})
    with pytest.raises(ValidationError, match="at most one option per window"):
        models.Plan.model_validate(payload)
