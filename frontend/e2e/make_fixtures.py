"""Regenerate the UI test fixtures in frontend/e2e/fixtures/ (run from backend/: see README).

These are TEST FIXTURES, not results. The run is hand-built through the real contracts. The
benchmark files come from the real ``aether.evaluation.benchmark`` driven by a FAKE runner whose
outcome is chosen per family to cover every reading the UI must render: a clear win, a tie and a
loss. Nothing here may be quoted as a benchmark result.

    cd backend && python ../frontend/e2e/make_fixtures.py
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

import numpy as np

from aether.config import load_scenario
from aether.contracts import (
    AcquisitionOption,
    BeliefSnapshot,
    CandidateUtility,
    ObservationOutcome,
    ObservationWindow,
    Plan,
    PolicyId,
    Regime,
    RejectionReason,
    RunRecord,
    ScheduleValidation,
    Selection,
    SimulatedAcquisition,
    SolverStatus,
    Source,
)
from aether.contracts.models import acquisition_option_id
from aether.evaluation.benchmark import _compare, benchmark
from aether.evaluation.metrics import evaluation_times
from aether.rng import keyed_rng
from aether.simulation.truth_types import SourceTruth, TruthHistory

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "fixtures"
UNIFORM = {Regime.PERSISTENT: 1 / 3, Regime.INTERMITTENT: 1 / 3, Regime.EPISODIC: 1 / 3}
# How sharp adaptive_eig's belief is per family (0.5 = no information): win, tie, loss coverage.
ADAPTIVE_SHARPNESS = {"m0_well_specified": 0.9, "m1_persistence_wrong": 0.85,
                      "m2_pod_optimistic": 0.5, "m3_forecast_overconfident": 0.8,
                      "m4_false_positives": 0.5, "r1_resource_scarce": 0.2}  # fmt: skip


def fixture_run_fn(bundle, policy, seed):
    cfg = bundle.model
    hours = int(cfg.horizon_hours)
    pattern = {"S0": np.ones(hours, bool), "S1": np.zeros(hours, bool),
               "S2": np.arange(hours) < hours // 2}  # fmt: skip
    truth = TruthHistory(
        epoch_utc=cfg.simulation_epoch_utc, hours=hours,
        sources={sid: SourceTruth(source_id=sid, regime=Regime.INTERMITTENT, median_flux_kg_h=300.0,
                                  active=a, flux_kg_h=np.where(a, 300.0, 0.0))
                 for sid, a in pattern.items()},
    )  # fmt: skip
    noise = keyed_rng(seed, "bootstrap", "ui-fixture", cfg.family, policy.value)
    sharp = ADAPTIVE_SHARPNESS[cfg.family] if policy is PolicyId.ADAPTIVE_EIG else 0.5
    beliefs = []
    for t in evaluation_times(cfg.simulation_epoch_utc, hours, cfg.evaluation.eval_interval_hours):
        h = truth.hour_index(t)
        for sid, a in pattern.items():
            p = sharp if a[h] else 1 - sharp
            p = float(np.clip(p + noise.normal(0, 0.08), 0.01, 0.99))
            beliefs.append(BeliefSnapshot(
                source_id=sid, state_time_utc=t, p_active=p, regime_probs=UNIFORM,
                flux_median_kg_h=300.0, flux_ci90_kg_h=(100.0, 900.0), entropy_bits=0.5,
                model_version="ui-fixture", evidence_ids=(), received_new_evidence=False,
            ))  # fmt: skip
    run = RunRecord(
        run_id=f"ui-fixture-{cfg.family}-{policy.value}-{seed}", policy_id=policy,
        scenario_id=cfg.scenario_id, family=cfg.family, seed=seed,
        model_config_hash=cfg.config_hash(), truth_config_hash=bundle.truth.config_hash(),
        code_version="ui-test-fixture",
        sources=tuple(Source(id=s, lon=-103.0, lat=32.0) for s in pattern), windows=(), plans=(),
        validations=(), utilities=(), acquisitions=(), beliefs=tuple(beliefs), events=(),
    )  # fmt: skip
    return run, truth


def few_seed_report(full: dict, runs_csv: Path, n: int) -> dict:
    """Recompute every comparison on the first ``n`` seeds (real stats, fewer pairs)."""
    rows = []
    with runs_csv.open() as fh:
        for r in csv.DictReader(fh):
            r["seed"] = int(r["seed"])
            for k, v in r.items():
                if k not in ("family", "policy", "run_id", "seed"):
                    r[k] = None if v == "" else float(v)
            rows.append(r)
    seeds = sorted({r["seed"] for r in rows})[:n]
    rows = [r for r in rows if r["seed"] in seeds]
    comps = [
        _compare(rows, c["family"], c["a"], c["b"], c["metric"], 10_000, 0.95,
                 full["protocol_version"])
        for c in full["comparisons"]
    ]  # fmt: skip
    return full | {"n_seeds": n, "comparisons": comps, "success_verdict": None, "holm_primary": {}}


def fixture_run(cfg) -> RunRecord:
    t0 = cfg.simulation_epoch_utc
    start = t0 + timedelta(hours=2)
    opt = AcquisitionOption(
        option_id=acquisition_option_id("w-S0-1", start), window_id="w-S0-1", start_utc=start,
        end_utc=start + timedelta(seconds=3), off_nadir_deg=12.0, sun_elevation_deg=41.0,
        los_unit_ecef=(0.0, 0.0, -1.0),
    )  # fmt: skip
    windows = (
        ObservationWindow(
            id="w-S0-1", spacecraft_id="vsat_a", sensor_id="vs_a_point_source", source_id="S0",
            start_utc=start, end_utc=start + timedelta(seconds=40), pass_id="p1", orbit_number=1,
            feasible=True, min_off_nadir_deg=12.0, options=(opt,), duration_s=3.0, energy_wh=0.2,
            data_bytes=306_000_000,
        ),
        ObservationWindow(
            id="w-S1-1", spacecraft_id="vsat_a", sensor_id="vs_a_point_source", source_id="S1",
            start_utc=start, end_utc=start + timedelta(seconds=40), pass_id="p1", orbit_number=1,
            feasible=False, rejection_reasons=(RejectionReason.DARK,), min_off_nadir_deg=30.0,
            duration_s=3.0, energy_wh=0.2, data_bytes=306_000_000,
        ),
    )  # fmt: skip
    plan = Plan(
        run_id="ui-fixture-run", policy_id=PolicyId.ADAPTIVE_EIG, revision=0, created_at_sim_utc=t0,
        cause="initial plan", objective_weights={"eig": 1.0}, candidate_window_ids=("w-S0-1",),
        selections=(Selection(window_id="w-S0-1", option_id=opt.option_id),),
        solver_status=SolverStatus.OPTIMAL, objective_value=0.42, best_bound=0.42, runtime_s=0.05,
        validation_ok=True,
    )  # fmt: skip
    beliefs = tuple(
        BeliefSnapshot(
            source_id=sid, state_time_utc=t, p_active=p, regime_probs=UNIFORM,
            flux_median_kg_h=300.0, flux_ci90_kg_h=(100.0, 900.0), entropy_bits=0.6,
            model_version="ui-fixture", evidence_ids=("acq-1",) if new else (),
            received_new_evidence=new,
        )
        for sid in ("S0", "S1")
        for t, p, new in ((t0, 0.4, False), (start + timedelta(minutes=1), 0.7 if sid == "S0" else 0.4,
                                                 sid == "S0"))
    )  # fmt: skip
    return RunRecord(
        run_id="ui-fixture-run", policy_id=PolicyId.ADAPTIVE_EIG, scenario_id=cfg.scenario_id,
        family=cfg.family, seed=1000, model_config_hash=cfg.config_hash(), truth_config_hash="t",
        code_version="ui-test-fixture",
        sources=(Source(id="S0", lon=-103.1, lat=32.1), Source(id="S1", lon=-102.9, lat=31.9)),
        windows=windows, plans=(plan,),
        validations=(ScheduleValidation(plan_revision=0, ok=True, violations=(),
                                        checker_version="ui-fixture"),),
        utilities=(CandidateUtility(
            window_id="w-S0-1", plan_revision=0, expected_info_gain_bits=0.42,
            decision_relevance=0.1, latency_s=0.0, resource_cost=0.1, p_valid_forecast=0.8,
            utility=0.42, integer_utility=4200),),
        acquisitions=(SimulatedAcquisition(
            id="acq-1", option_id=opt.option_id, window_id="w-S0-1", source_id="S0",
            spacecraft_id="vsat_a", sensor_id="vs_a_point_source", time_utc=start,
            outcome=ObservationOutcome.DETECTION, measured_flux_kg_h=320.0, off_nadir_deg=12.0,
            wind_estimate_m_s=4.0, scene_cloud_fraction=0.1, rng_key="ui-fixture"),),
        beliefs=beliefs, events=(),
    )  # fmt: skip


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = load_scenario(REPO / "configs" / "base.yaml").model
    (OUT / "run.json").write_text(fixture_run(cfg).model_dump_json(indent=1))
    with tempfile.TemporaryDirectory() as tmp:
        full = benchmark(REPO / "experiments/protocol.yaml", REPO / "experiments/seeds_dev.txt",
                         tmp, run_fn=fixture_run_fn)  # fmt: skip
        with (Path(tmp) / "benchmark-results.csv").open() as fh:
            results = [r for r in csv.DictReader(fh) if r["breakdown"] == "all"]
        few = few_seed_report(full, Path(tmp) / "benchmark-runs.csv", 5)
    (OUT / "benchmark-ci-30.json").write_text(json.dumps(full, indent=1))
    (OUT / "benchmark-ci-5.json").write_text(json.dumps(few, indent=1))
    (OUT / "benchmark-results.json").write_text(json.dumps(results, indent=0))
    # Project-mode views, exactly as the read-only API serves them for this repository.
    from fastapi.testclient import TestClient

    from aether.api import create_app

    with tempfile.TemporaryDirectory() as empty_runs:
        api = TestClient(create_app(run_root=empty_runs, project_root=REPO))
        for route, name in (("/api/project", "project.json"),
                            ("/api/benchmark-protocol", "protocol.json")):  # fmt: skip
            resp = api.get(route)
            resp.raise_for_status()
            (OUT / name).write_text(json.dumps(resp.json(), indent=1))
    print(f"wrote fixtures to {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
