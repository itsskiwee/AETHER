"""Benchmark runner (EVL-04): every family x policy x seed, scored against hidden truth.

Writes to ``out_dir``:

- ``benchmark-runs.csv``: one row per (family, policy, seed) with every score from ``score_run``.
- ``benchmark-results.csv``: per family x policy x metric x breakdown: mean, SD, n_seeds,
  n defined, n undefined (``n_seeds`` is the column the UI reads for its seed count).
  Denominators travel with every rate.
- ``benchmark-confidence-intervals.json``: paired bootstrap comparisons (primary and mandatory
  secondary, on the primary metric and on high-impact recall), Holm-adjusted family results, the
  success verdict, total checker violations and a provenance manifest.

The holdout seed list is refused unless the protocol is locked (``protocol.check_seed_access``).
Reference policies (``random_feasible``, ``oracle``) are not benchmarked here; they feed G4.5.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path

import numpy as np

from aether.config import ScenarioBundle, load_scenario
from aether.contracts.enums import PolicyId
from aether.contracts.models import RunRecord
from aether.evaluation.metrics import Score, score_run
from aether.evaluation.protocol import check_seed_access, file_sha256, load_protocol, read_seeds
from aether.evaluation.stats import PairedBootstrap, holm, paired_bootstrap, success_verdict
from aether.simulation.truth_types import TruthHistory

RunFn = Callable[[ScenarioBundle, PolicyId, int], tuple[RunRecord, TruthHistory]]

_KEY = re.compile(r"^(?P<metric>[^\[]+)(?:\[(?P<breakdown>[^\]]+)\])?$")
RECALL_METRIC = "high_impact_recall_at_5"
# Which sign of (a - b) favours policy a. Written into every comparison so no reader has to guess.
LOWER_IS_BETTER = {"brier_active_state", "log_loss_active_state", "ece_active_state",
                   "time_to_corroboration_hours", "solver_runtime_p95_s"}  # fmt: skip
HIGHER_IS_BETTER = {RECALL_METRIC, "valid_acquisition_fraction"}
MISSPECIFIED_FAMILIES = (
    "m1_persistence_wrong", "m2_pod_optimistic", "m3_forecast_overconfident", "m4_false_positives",
)  # fmt: skip


def metric_direction(metric: str) -> str | None:
    """ "lower" or "higher" is better; None when the metric has a target, not a direction."""
    if metric in LOWER_IS_BETTER:
        return "lower"
    if metric in HIGHER_IS_BETTER:
        return "higher"
    return None


def default_run_fn(bundle: ScenarioBundle, policy_id: PolicyId, seed: int):
    """Run through the L1 runner, then regenerate the run's truth from the same seed.

    Truth is a deterministic function of (truth config, sources, seed), so it does not need to
    travel inside the RunRecord. The run must report the seed it was asked for.
    """
    from aether.simulation.runner import run_policy
    from aether.simulation.truth import generate_truth

    run = run_policy(bundle, policy_id, seed)
    if run.seed != seed:
        raise RuntimeError(f"runner returned seed {run.seed}, expected {seed}")
    return run, generate_truth(bundle.truth, run.sources, seed=seed)


def _split(key: str) -> tuple[str, str]:
    m = _KEY.match(key)
    if m is None:
        raise ValueError(f"unparseable score key {key!r}")
    return m["metric"], m["breakdown"] or "all"


def _write_csv(path: Path, rows: list[dict], fields: Sequence[str]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fields), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})


def _aggregate(rows: list[dict], score_keys: Sequence[str]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["family"], r["policy"])].append(r)
    out = []
    for (family, policy), grp in sorted(groups.items()):
        for key in score_keys:
            metric, breakdown = _split(key)
            vals = [r[key] for r in grp if r[key] is not None]
            out.append({
                "family": family, "policy": policy, "metric": metric, "breakdown": breakdown,
                "mean": float(np.mean(vals)) if vals else None,
                "sd": float(np.std(vals, ddof=1)) if len(vals) > 1 else None,
                "n_seeds": len({r["seed"] for r in grp}),
                "n_defined": len(vals), "n_undefined": len(grp) - len(vals),
            })  # fmt: skip
    return out


def _compare(
    rows: list[dict], family: str, a: str, b: str, metric: str, resamples: int, level: float,
    seed: int,
) -> dict:  # fmt: skip
    by_seed = defaultdict(dict)
    for r in rows:
        if r["family"] == family and r["policy"] in (a, b):
            by_seed[r["seed"]][r["policy"]] = r[metric]
    pairs = [(v[a], v[b]) for _, v in sorted(by_seed.items())
             if v.get(a) is not None and v.get(b) is not None]  # fmt: skip
    excluded = len(by_seed) - len(pairs)
    base = {"family": family, "a": a, "b": b, "metric": metric,
            "better_direction": metric_direction(metric), "n_pairs": len(pairs),
            "n_excluded_undefined": excluded}  # fmt: skip
    if len(pairs) < 2:
        return base | {"result": None, "note": "insufficient samples (< 2 defined pairs)"}
    res = paired_bootstrap([p[0] for p in pairs], [p[1] for p in pairs], resamples, level,
                           seed=seed, comparison_id=f"{family}|{metric}|{a}-{b}")  # fmt: skip
    return base | {"result": asdict(res)}


def benchmark(
    protocol_path: str | Path,
    seeds_path: str | Path,
    out_dir: str | Path,
    run_fn: RunFn = default_run_fn,
) -> dict:
    protocol_path, seeds_path, out_dir = Path(protocol_path), Path(seeds_path), Path(out_dir)
    proto = load_protocol(protocol_path)
    lock_tag = check_seed_access(proto, protocol_path, seeds_path)
    seeds = read_seeds(seeds_path)
    repo = protocol_path.resolve().parent.parent
    scenarios = repo / "configs" / "scenarios"
    base = repo / proto.base_config

    rows: list[dict] = []
    score_keys: list[str] = []
    config_hashes: dict[str, dict[str, str]] = {}
    for family in proto.families:
        bundle = load_scenario(base, scenarios / f"{family}.yaml")
        config_hashes[family] = {"model": bundle.model.config_hash(),
                                 "truth": bundle.truth.config_hash()}  # fmt: skip
        for seed in seeds:
            for policy in proto.policies:
                run, truth = run_fn(bundle, policy, seed)
                if run.policy_id is not policy or run.family != family or run.seed != seed:
                    raise RuntimeError(f"runner mislabelled run {run.run_id}")
                scores: dict[str, Score] = score_run(run, truth, bundle.model)
                for k in scores:
                    if k not in score_keys:
                        score_keys.append(k)
                rows.append({"family": family, "policy": policy.value, "seed": seed,
                             "run_id": run.run_id} | scores)  # fmt: skip

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "benchmark-runs.csv", rows, ["family", "policy", "seed", "run_id",
                                                       *score_keys])  # fmt: skip
    agg = _aggregate(rows, score_keys)
    _write_csv(out_dir / "benchmark-results.csv", agg,
               ["family", "policy", "metric", "breakdown", "mean", "sd", "n_seeds",
                "n_defined", "n_undefined"])  # fmt: skip

    res, level = proto.analysis.resamples, proto.analysis.level
    boot_seed = proto.protocol_version
    comparisons = []
    for family in proto.families:
        for a, b in (proto.primary_comparison, proto.mandatory_secondary_comparison):
            for metric in (proto.primary_metric, RECALL_METRIC):
                comparisons.append(_compare(rows, family, a.value, b.value, metric, res, level,
                                            boot_seed))  # fmt: skip

    a, b = (p.value for p in proto.primary_comparison)
    primary = {
        c["family"]: PairedBootstrap(**c["result"])
        for c in comparisons
        if c["a"] == a and c["b"] == b and c["metric"] == proto.primary_metric and c["result"]
    }
    misspecified = {f: primary[f].p_value for f in MISSPECIFIED_FAMILIES if f in primary}
    holm_primary = {f: asdict(h) for f, h in holm(misspecified).items()}
    violations = int(sum(r["feasibility_checker_violations"] or 0 for r in rows))
    verdict = None
    if "m0_well_specified" in primary:
        verdict = asdict(success_verdict(primary, violations))

    report = {
        "protocol_version": proto.protocol_version,
        "protocol_sha256": file_sha256(protocol_path),
        "protocol_locked": proto.locked,
        "lock_tag": lock_tag,
        "seeds_file": str(seeds_path),
        "seeds_sha256": file_sha256(seeds_path),
        "n_seeds": len(seeds),
        "config_hashes": config_hashes,
        "total_checker_violations": violations,
        "comparisons": comparisons,
        "holm_primary": holm_primary,  # primary comparison, m1..m4, family-wise alpha 0.05
        "success_verdict": verdict,
        "note": "Tuning-seed results; not a pre-registered test." if lock_tag is None else None,
    }
    text = json.dumps(report, indent=2)
    (out_dir / "benchmark-confidence-intervals.json").write_text(text)
    return json.loads(text)  # return exactly what was written (tuples become lists)
