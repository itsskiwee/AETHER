"""EVL-04: benchmark pipeline with a fake runner (the real runner is INT-03).

The fake gives adaptive_eig well-calibrated beliefs and every other policy p = 0.5 plus seeded
noise, so the expected verdict is known: adaptive_eig wins every family.
"""

import csv
import json

import numpy as np
import pytest

from aether.contracts import BeliefSnapshot, PolicyId, Regime, RunRecord, Source
from aether.evaluation.benchmark import (
    MISSPECIFIED_FAMILIES,
    _compare,
    benchmark,
    metric_direction,
)
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


def test_undefined_pairs_are_excluded_not_zeroed():
    rows = [{"family": "f", "policy": pol, "seed": seed, "m": val}
            for seed, (va, vb) in enumerate([(0.5, 0.25), (None, 0.5), (1.0, 0.5), (0.75, None)])
            for pol, val in (("a", va), ("b", vb))]  # fmt: skip
    c = _compare(rows, "f", "a", "b", "m", resamples=100, level=0.95, seed=1)
    assert (c["n_pairs"], c["n_excluded_undefined"]) == (2, 2)
    assert c["result"]["mean_diff"] == pytest.approx(0.375)  # (0.25 + 0.5) / 2, no zero-filling
    one = _compare(rows[:4], "f", "a", "b", "m", resamples=100, level=0.95, seed=1)
    assert one["result"] is None and "insufficient" in one["note"]


def test_comparisons_state_direction_and_holm(report):
    rep, _ = report
    dirs = {c["metric"]: c["better_direction"] for c in rep["comparisons"]}
    assert dirs == {"brier_active_state": "lower", "high_impact_recall_at_5": "higher"}
    assert set(rep["holm_primary"]) == set(MISSPECIFIED_FAMILIES)
    assert all(h["reject"] for h in rep["holm_primary"].values())
    assert metric_direction("flux_interval_coverage_90") is None  # has a target, not a direction


def test_holdout_refused_while_protocol_unlocked(repo_root, tmp_path):
    with pytest.raises(ProtocolLockError):
        holdout = repo_root / "experiments/seeds_holdout.txt"
        benchmark(repo_root / "experiments/protocol.yaml", holdout, tmp_path, run_fn=fake_run)


@pytest.mark.parametrize(
    "update",
    [{"policy_id": PolicyId.ORACLE}, {"family": "m1_persistence_wrong"}, {"seed": -1}],
    ids=["policy", "family", "seed"],
)
def test_mislabelled_run_rejected(repo_root, tmp_path, update):
    def wrong(bundle, policy, seed):
        run, truth = fake_run(bundle, policy, seed)
        return run.model_copy(update=update), truth

    with pytest.raises(RuntimeError, match="mislabelled"):
        benchmark(repo_root / "experiments/protocol.yaml",
                  repo_root / "experiments/seeds_dev.txt", tmp_path, run_fn=wrong)  # fmt: skip


def test_development_comparison_is_preliminary_and_round_trippable(repo_root, tmp_path):
    from aether.evaluation.development import POLICIES, development_comparison

    report = development_comparison(repo_root, tmp_path, (1000, 1001), run_fn=fake_run)
    assert report["input_datasets"] == [None]  # the fake runs carry no dataset reference
    assert report["preliminary"] and report["insufficient_samples"]
    assert "insufficient samples" in report["note"]
    assert report["success_verdict"] is None
    assert {c["b"] for c in report["comparisons"]} == {"largest_first", "greedy_eig"}
    assert all(c["n_pairs"] == 2 and c["result"] for c in report["comparisons"])
    runs = [RunRecord.model_validate_json(p.read_text()) for p in tmp_path.glob("*/run.json")]
    assert len(runs) == 2 * len(POLICIES)
    timing = json.loads((tmp_path / "development-timing.json").read_text())
    assert timing["complete_comparison_elapsed_s"] > 0
    assert all(r["complete_run_elapsed_s"] > 0 for r in timing["runs"])


@pytest.mark.parametrize("seeds", [(), (1000, 1000), (2000,)])
def test_development_comparison_rejects_unapproved_seeds_before_running(repo_root, tmp_path, seeds):
    from aether.evaluation.development import development_comparison

    def forbidden(*args):
        pytest.fail("runner must not execute for rejected seed request")

    with pytest.raises(ValueError, match="approved development seeds"):
        development_comparison(repo_root, tmp_path, seeds, run_fn=forbidden)


@pytest.mark.parametrize("synthetic_only", [False, True])
def test_synthetic_only_switch_reaches_every_run(repo_root, tmp_path, synthetic_only):
    """The benchmark switch must change what the runner sees, not only a label."""
    seen = set()

    def recording(bundle, policy, seed):
        seen.add((bundle.model.sources.plume_dataset is None,
                  bundle.truth.sources.plume_dataset is None))  # fmt: skip
        return fake_run(bundle, policy, seed)

    report = benchmark(repo_root / "experiments/protocol.yaml",
                       repo_root / "experiments/seeds_dev.txt", tmp_path, run_fn=recording,
                       synthetic_only=synthetic_only)  # fmt: skip
    assert seen == {(synthetic_only, synthetic_only)}
    assert report["synthetic_only"] is synthetic_only
