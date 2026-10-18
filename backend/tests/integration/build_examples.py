"""Regenerate contract-valid UI examples: ``python -m tests.integration.build_examples``."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aether.contracts.enums import EventType, ObservationOutcome, PolicyId, Regime, RejectionReason
from aether.contracts.models import (
    AcquisitionOption,
    BeliefSnapshot,
    CandidateUtility,
    ObservationWindow,
    Plan,
    RunEvent,
    RunRecord,
    ScheduleValidation,
    Selection,
    SimulatedAcquisition,
    Source,
    acquisition_option_id,
)

ROOT = Path(__file__).resolve().parents[3]
EPOCH = datetime(2025, 1, 1, tzinfo=UTC)
HASH = hashlib.sha256(b"AETHER documentation example; synthetic only").hexdigest()


def _payload_sha256(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build(policy: PolicyId) -> RunRecord:
    run_id = f"example-{policy.value}"
    sources = tuple(
        Source(id=f"source-{i:03}", lon=-103.0 + i * 0.02, lat=32.0 + i * 0.02) for i in range(2)
    )
    windows = []
    options = []
    for i in range(6):
        source = sources[i % len(sources)]
        start = EPOCH + timedelta(hours=i + 1)
        end = start + timedelta(seconds=120)
        option = AcquisitionOption(
            option_id=acquisition_option_id(f"window-{i:03}", start),
            window_id=f"window-{i:03}",
            start_utc=start,
            end_utc=start + timedelta(seconds=30),
            off_nadir_deg=4.0,
            sun_elevation_deg=35.0,
            los_unit_ecef=(1.0, 0.0, 0.0),
        )
        options.append(option)
        windows.append(
            ObservationWindow(
                id=f"window-{i:03}",
                spacecraft_id="VS-A",
                sensor_id="EMIT_SIM",
                source_id=source.id,
                start_utc=start,
                end_utc=end,
                pass_id=f"pass-{i // 2:02}",
                orbit_number=100 + i // 2,
                feasible=True,
                min_off_nadir_deg=4.0,
                options=(option,),
                duration_s=30.0,
                energy_wh=18.0,
                data_bytes=100_000_000,
            )
        )
    windows.append(
        ObservationWindow(
            id="window-rejected",
            spacecraft_id="VS-A",
            sensor_id="EMIT_SIM",
            source_id=sources[0].id,
            start_utc=EPOCH + timedelta(hours=8),
            end_utc=EPOCH + timedelta(hours=9),
            pass_id="pass-rejected",
            orbit_number=104,
            feasible=False,
            rejection_reasons=(RejectionReason.DARK,),
            min_off_nadir_deg=12.0,
            duration_s=30.0,
            energy_wh=18.0,
            data_bytes=100_000_000,
        )
    )
    causes = ("initial", "informative_acquisition", "forecast_revision")
    plans = []
    validations = []
    events = [
        RunEvent(
            event_id=f"{run_id}:event:{i:06}",
            run_id=run_id,
            sequence_number=i,
            event_time_sim_utc=EPOCH + timedelta(hours=20 if i == 8 else i),
            event_type=EventType.FORECAST_REVISED if i == 8 else EventType.PLAN_REQUESTED,
            actor="weather" if i == 8 else "simulation",
            payload={
                "cause": "forecast_revision" if i in (7, 8) else causes[min((i - 1) // 3, 2)],
                "injected": i == 8,
            },
            payload_sha256=_payload_sha256(
                {
                    "cause": "forecast_revision" if i in (7, 8) else causes[min((i - 1) // 3, 2)],
                    "injected": i == 8,
                }
            ),
            config_hash=HASH,
            model_version="p0-0",
        )
        for i in range(1, 10)
    ]
    for revision, cause in enumerate(causes):
        selections = tuple(
            Selection(
                window_id=f"window-{revision * 2 + offset:03}",
                option_id=options[revision * 2 + offset].option_id,
            )
            for offset in range(2)
        )
        plan = Plan(
            run_id=run_id,
            policy_id=policy,
            revision=revision,
            created_at_sim_utc=EPOCH + timedelta(hours=(0, 10, 20)[revision]),
            cause=cause,
            objective_weights={
                "information": 1.0,
                "decision": 1.0,
                "latency": 0.0,
                "resource": 0.0,
            },
            candidate_window_ids=tuple(window.id for window in windows if window.feasible),
            selections=selections,
            solver_status="HEURISTIC" if policy is PolicyId.LARGEST_FIRST else "OPTIMAL",
            objective_value=1.5 - revision * 0.1,
            best_bound=1.5 - revision * 0.1,
            runtime_s=None,
            validation_ok=True,
        )
        plans.append(plan)
        validations.append(
            ScheduleValidation(
                plan_revision=revision, ok=True, violations=(), checker_version="example-only"
            )
        )
        events.extend(
            (
                RunEvent(
                    event_id=f"{run_id}:plan:{revision}:proposed",
                    run_id=run_id,
                    sequence_number=10 + revision * 2,
                    event_time_sim_utc=plan.created_at_sim_utc,
                    event_type=EventType.PLAN_PROPOSED,
                    actor=policy.value,
                    payload={"revision": revision, "cause": cause},
                    payload_sha256=_payload_sha256({"revision": revision, "cause": cause}),
                    config_hash=HASH,
                    model_version="p0-0",
                ),
                RunEvent(
                    event_id=f"{run_id}:plan:{revision}:validated",
                    run_id=run_id,
                    sequence_number=11 + revision * 2,
                    event_time_sim_utc=plan.created_at_sim_utc,
                    event_type=EventType.PLAN_VALIDATED,
                    actor="independent_checker",
                    payload={"revision": revision, "ok": True},
                    payload_sha256=_payload_sha256({"revision": revision, "ok": True}),
                    config_hash=HASH,
                    model_version="p0-0",
                ),
            )
        )
    acquisitions = []
    utilities = []
    for i, option in enumerate(options):
        window = windows[i]
        outcome = tuple(ObservationOutcome)[i % len(ObservationOutcome)]
        acquisitions.append(
            SimulatedAcquisition(
                id=f"acq-{i:03}",
                option_id=option.option_id,
                window_id=window.id,
                source_id=window.source_id,
                spacecraft_id=window.spacecraft_id,
                sensor_id=window.sensor_id,
                time_utc=option.start_utc,
                outcome=outcome,
                measured_flux_kg_h=75.0 if outcome is ObservationOutcome.DETECTION else None,
                off_nadir_deg=option.off_nadir_deg,
                wind_estimate_m_s=4.5,
                scene_cloud_fraction=0.15,
                rng_key=f"example:{i}",
            )
        )
        utilities.append(
            CandidateUtility(
                window_id=window.id,
                plan_revision=min(i // 2, 2),
                expected_info_gain_bits=0.2 + i * 0.01,
                decision_relevance=0.03,
                latency_s=3600.0 * (i + 1),
                resource_cost=0.05,
                p_valid_forecast=0.85,
                utility=0.25 + i * 0.01,
                integer_utility=250 + i * 10,
            )
        )
    beliefs = tuple(
        BeliefSnapshot(
            source_id=source.id,
            state_time_utc=EPOCH + timedelta(hours=hour),
            p_active=0.42 + 0.02 * hour / 6,
            regime_probs={Regime.EPISODIC: 0.3, Regime.INTERMITTENT: 0.4, Regime.PERSISTENT: 0.3},
            flux_median_kg_h=52.0,
            flux_ci90_kg_h=(12.0, 180.0),
            entropy_bits=0.88,
            model_version="p0-0",
            evidence_ids=tuple(
                a.id
                for a in acquisitions
                if a.source_id == source.id and a.time_utc <= EPOCH + timedelta(hours=hour)
            ),
            received_new_evidence=any(
                a.source_id == source.id and a.time_utc == EPOCH + timedelta(hours=hour)
                for a in acquisitions
            ),
        )
        for source in sources
        for hour in (0, 6, 12, 18)
    )
    return RunRecord(
        run_id=run_id,
        policy_id=policy,
        scenario_id="docs-example",
        family="m0_well_specified",
        seed=1000,
        model_config_hash=HASH,
        truth_config_hash=HASH,
        code_version="0.1.0",
        sources=sources,
        windows=tuple(windows),
        plans=tuple(plans),
        validations=tuple(validations),
        utilities=tuple(utilities),
        acquisitions=tuple(acquisitions),
        beliefs=beliefs,
        events=tuple(sorted(events, key=lambda event: event.sequence_number)),
    )


def main():
    EXAMPLES = ROOT / "docs" / "examples"
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    for policy, name in (
        (PolicyId.ADAPTIVE_EIG, "run.json"),
        (PolicyId.LARGEST_FIRST, "run_largest_first.json"),
    ):
        record = build(policy)
        (EXAMPLES / name).write_text(
            json.dumps(record.model_dump(mode="json"), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
