"""EVL-08 gate driver, resumable run matrix, and SCI-10 calibration analysis."""

import json

import numpy as np
import pytest

from aether.contracts import PolicyId
from aether.evaluation import matrix
from aether.evaluation.calibration import calibration_report
from aether.evaluation.gate import gate_from_records, run_gate
from aether.evaluation.protocol import ProtocolLockError
from aether.rng import keyed_rng
from tests.unit.test_evaluation_benchmark import fake_run

CALLS = []


def counting_fake_run(bundle, policy, seed):
    CALLS.append((bundle.model.family, policy.value, seed))
    run, truth = fake_run(bundle, PolicyId.ADAPTIVE_EIG if policy is PolicyId.ORACLE else policy,
                          seed)  # fmt: skip
    return run.model_copy(update={"policy_id": policy}), truth


def _rec(brier, violations=0, acq=10, passes=5):
    return {
        "scores": {"brier_active_state": brier, "feasibility_checker_violations": violations},
        "capacity": {"passes": passes, "passes_per_72h": passes, "acquisitions": acq,
                     "acquisitions_per_pass": acq / passes, "capacity_to_demand_ratio": 0.1},
    }  # fmt: skip


def test_gate_rule_uses_sd_not_se():
    seeds = list(range(10))
    oracle = [0.10] * 10
    # mean gap 0.05, SD ~0.032: significant by SE, but the 2 x SD rule fails.
    rand = [0.10 + g for g in (0.0, 0.1, 0.0, 0.1, 0.0, 0.1, 0.05, 0.05, 0.05, 0.05)]
    recs = {("m0", "oracle", s): _rec(o) for s, o in zip(seeds, oracle, strict=False)}
    recs |= {("m0", "random_feasible", s): _rec(r) for s, r in zip(seeds, rand, strict=False)}
    out = gate_from_records(recs, ["m0"], seeds)["m0"]
    assert out["gap_mean_random_minus_oracle"] == pytest.approx(0.05)
    assert out["gap_mean_random_minus_oracle"] > 2 * out["se_paired"]
    assert not out["passed"]
    assert out["seeds_where_oracle_better"] == 7
    assert out["capacity_random_feasible"]["acquisitions_per_pass"]["mean"] == pytest.approx(2.0)


def test_gate_counts_reference_violations():
    seeds = [1, 2]
    recs = {("m0", "oracle", s): _rec(0.1, violations=1) for s in seeds}
    recs |= {("m0", "random_feasible", s): _rec(0.3 + s / 100) for s in seeds}
    out = gate_from_records(recs, ["m0"], seeds)["m0"]
    assert out["passed"] and out["reference_checker_violations"] == 2


def test_gate_refuses_holdout_seeds(repo_root, tmp_path):
    with pytest.raises(ProtocolLockError):
        run_gate(repo_root, tmp_path, ["m0_well_specified"],
                 seeds_file="experiments/seeds_holdout.txt", run_fn=counting_fake_run)  # fmt: skip


def test_gate_end_to_end_and_resume(repo_root, tmp_path):
    CALLS.clear()
    rep = run_gate(repo_root, tmp_path, ["m0_well_specified"], seed_subset=(1000, 1001),
                   run_fn=counting_fake_run)  # fmt: skip
    assert len(CALLS) == 4
    assert rep["seed_subset_only"] and rep["seeds"] == [1000, 1001]
    assert set(rep["per_family"]) == {"m0_well_specified"}
    assert (tmp_path / "gate-seeds.csv").read_text().count("\n") == 3
    written = json.loads((tmp_path / "gate.json").read_text())
    assert written["overall_passed"] == rep["overall_passed"]
    # Rerun reuses every record whose identity matches: no new runs.
    run_gate(repo_root, tmp_path, ["m0_well_specified"], seed_subset=(1000, 1001),
             run_fn=counting_fake_run)  # fmt: skip
    assert len(CALLS) == 4
    # A stale identity (e.g. changed config hash) is rerun, never reused.
    path = tmp_path / "records/m0_well_specified/oracle/1000.json"
    rec = json.loads(path.read_text())
    rec["identity"]["model_config_hash"] = "stale"
    path.write_text(json.dumps(rec))
    run_gate(repo_root, tmp_path, ["m0_well_specified"], seed_subset=(1000, 1001),
             run_fn=counting_fake_run)  # fmt: skip
    assert CALLS[-1] == ("m0_well_specified", "oracle", 1000) and len(CALLS) == 5


def test_seed_subset_must_be_tuning_seeds(repo_root, tmp_path):
    with pytest.raises(ValueError, match="tuning"):
        run_gate(repo_root, tmp_path, ["m0_well_specified"], seed_subset=(1,),
                 run_fn=counting_fake_run)  # fmt: skip


def test_calibration_points_match_scores(repo_root, tmp_path):
    from aether.evaluation.metrics import score_run

    bundle = matrix.family_bundle(repo_root, "configs/base.yaml", "m0_well_specified", 1000)
    run, truth = fake_run(bundle, PolicyId.LARGEST_FIRST, 1000)
    pts = matrix.calibration_points(run, truth, bundle.model)
    scores = score_run(run, truth, bundle.model)
    assert len(pts) == scores["n_points"]
    assert np.mean([(p[2] - p[3]) ** 2 for p in pts]) == pytest.approx(
        scores["brier_active_state"], abs=1e-15
    )
    cover = np.mean([p[4] <= p[6] <= p[5] for p in pts])
    assert cover == pytest.approx(scores["flux_interval_coverage_90"])


def _synthetic_points(seed, calibrated: bool, n=400):
    """Forecast p ~ U(0,1); z ~ Bernoulli(p) if calibrated else Bernoulli(p**3).

    Flux: ln Q ~ N(0,1) with the exact 90% interval, so expected coverage is 0.90.
    """
    rng = keyed_rng(seed, "bootstrap", "calibration-test")
    p = rng.uniform(0, 1, n)
    z = (rng.uniform(0, 1, n) < (p if calibrated else p**3)).astype(int)
    q = np.exp(rng.normal(0, 1, n))
    lo, hi = np.exp(-1.6448536), np.exp(1.6448536)
    return [[float(i % 12) * 6, f"S{i}", float(p[i]), int(z[i]), lo, hi, float(q[i])]
            for i in range(n)]  # fmt: skip


def test_calibrated_forecasts_pass_and_miscalibrated_fail():
    good = calibration_report({s: _synthetic_points(s, True) for s in range(30)}, 1000, 1, "good")
    cov = good["flux_interval_coverage_90"]
    assert cov["within_band"]
    lo, hi = cov["all_points"]["ci95_seed_cluster"]
    assert lo <= 0.90 <= hi
    assert len(good["bins_ci_excluding_zero"]) <= 1
    bad = calibration_report({s: _synthetic_points(s, False) for s in range(30)}, 1000, 1, "bad")
    assert len(bad["bins_ci_excluding_zero"]) >= 5
    assert bad["calibration_in_the_large"]["ci95_seed_cluster"][1] < 0


def test_calibration_is_seeded_and_needs_two_seeds():
    pts = {s: _synthetic_points(s, True, 50) for s in range(5)}
    assert calibration_report(pts, 200, 3, "x") == calibration_report(pts, 200, 3, "x")
    with pytest.raises(ValueError):
        calibration_report({1: pts[1]})


def test_code_identity_change_forces_rerun(repo_root, tmp_path, monkeypatch):
    CALLS.clear()
    args = (repo_root, tmp_path, ["m0_well_specified"])
    run_gate(*args, seed_subset=(1000, 1001), run_fn=counting_fake_run)
    assert len(CALLS) == 4
    rec = json.loads((tmp_path / "records/m0_well_specified/oracle/1000.json").read_text())
    assert rec["identity"]["code_sha256"] == matrix.code_sha256()
    monkeypatch.setattr(matrix, "_CODE_SHA256", "0" * 64)  # simulate an edited runner/planner
    run_gate(*args, seed_subset=(1000, 1001), run_fn=counting_fake_run)
    assert len(CALLS) == 8


def test_code_sha256_is_stable_hex():
    assert matrix.code_sha256() == matrix.code_sha256()
    assert len(matrix.code_sha256()) == 64
