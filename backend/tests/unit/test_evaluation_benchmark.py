"""EVL-04: benchmark pipeline with a fake runner (the real runner is INT-03).

The fake gives adaptive_eig well-calibrated beliefs and every other policy p = 0.5 plus seeded
noise, so the expected verdict is known: adaptive_eig wins every family.
"""

import csv
import json

import numpy as np
import pytest

from aether.contracts import BeliefSnapshot, PolicyId, Regime, RunRecord, Source
from aether.evaluation.benchmark import benchmark
from aether.evaluation.metrics import evaluation_times
from aether.evaluation.protocol import ProtocolLockError
from aether.rng import keyed_rng
from aether.simulation.truth_types import SourceTruth, TruthHistory

UNIFORM = {Regime.PERSISTENT: 1 / 3, Regime.INTERMITTENT: 1 / 3, Regime.EPISODIC: 1 / 3}


def fake_run(bundle, policy, seed):
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
    noise = keyed_rng(seed, "bootstrap", "fake-run", policy.value)
    beliefs = []
    for t in evaluation_times(cfg.simulation_epoch_utc, hours, cfg.evaluation.eval_interval_hours):
        h = truth.hour_index(t)
        for sid, a in pattern.items():
            if policy is PolicyId.ADAPTIVE_EIG:
                p = 0.9 if a[h] else 0.1
            else:
                p = float(np.clip(0.5 + noise.normal(0, 0.05), 0.01, 0.99))
            beliefs.append(BeliefSnapshot(
                source_id=sid, state_time_utc=t, p_active=p, regime_probs=UNIFORM,
                flux_median_kg_h=300.0, flux_ci90_kg_h=(100.0, 900.0), entropy_bits=0.5,
                model_version="fake", evidence_ids=(), received_new_evidence=False))  # fmt: skip
    run = RunRecord(
        run_id=f"{cfg.family}-{policy.value}-{seed}", policy_id=policy, scenario_id=cfg.scenario_id,
        family=cfg.family, seed=seed, model_config_hash=cfg.config_hash(),
        truth_config_hash=bundle.truth.config_hash(), code_version="fake",
        sources=tuple(Source(id=s, lon=-103.0, lat=32.0) for s in pattern), windows=(), plans=(),
        validations=(), utilities=(), acquisitions=(), beliefs=tuple(beliefs), events=(),
    )  # fmt: skip
    return run, truth


@pytest.fixture(scope="module")
def report(repo_root, tmp_path_factory):
    out = tmp_path_factory.mktemp("bench")
    rep = benchmark(repo_root / "experiments/protocol.yaml",
                    repo_root / "experiments/seeds_dev.txt", out, run_fn=fake_run)  # fmt: skip
    return rep, out


def test_outputs_written_with_denominators(report):
    rep, out = report
    rows = list(csv.DictReader((out / "benchmark-runs.csv").open()))
    assert len(rows) == 6 * 30 * 5  # families x dev seeds x policies
    agg = list(csv.DictReader((out / "benchmark-results.csv").open()))
    brier = [r for r in agg if r["metric"] == "brier_active_state" and r["breakdown"] == "all"]
    assert len(brier) == 6 * 5 and all(r["n_defined"] == r["n_seeds"] == "30" for r in brier)
    regimes = {r["breakdown"] for r in agg if r["metric"] == "brier_active_state"}
    assert {"regime=PERSISTENT", "observed=yes", "observed=no"} <= regimes
    assert json.loads((out / "benchmark-confidence-intervals.json").read_text()) == rep


def test_known_effect_is_detected(report):
    rep, _ = report
    prim = [c for c in rep["comparisons"] if c["a"] == "adaptive_eig" and c["b"] == "largest_first"
            and c["metric"] == "brier_active_state"]  # fmt: skip
    assert len(prim) == 6
    assert all(c["result"]["hi"] < 0 for c in prim)
    assert rep["success_verdict"]["success"] is True
    assert rep["lock_tag"] is None and "Tuning-seed" in rep["note"]


def test_undefined_recall_is_excluded_and_counted(report):
    rep, _ = report
    # every fake source has mean rate 300 or 150 or 0; only S0 (300) clears 278 kg/h, so recall is
    # defined on every seed here; the comparison reports how many pairs were excluded.
    rec = [c for c in rep["comparisons"] if c["metric"] == "high_impact_recall_at_5"]
    assert all(c["n_excluded_undefined"] == 0 and c["n_pairs"] == 30 for c in rec)


def test_holdout_refused_while_protocol_unlocked(repo_root, tmp_path):
    with pytest.raises(ProtocolLockError):
        holdout = repo_root / "experiments/seeds_holdout.txt"
        benchmark(repo_root / "experiments/protocol.yaml", holdout, tmp_path, run_fn=fake_run)


def test_mislabelled_run_rejected(repo_root, tmp_path):
    def wrong(bundle, policy, seed):
        run, truth = fake_run(bundle, policy, seed)
        return run.model_copy(update={"policy_id": PolicyId.ORACLE}), truth

    with pytest.raises(RuntimeError, match="mislabelled"):
        benchmark(repo_root / "experiments/protocol.yaml",
                  repo_root / "experiments/seeds_dev.txt", tmp_path, run_fn=wrong)  # fmt: skip
