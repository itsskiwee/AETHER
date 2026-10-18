"""Small, explicitly preliminary offline development comparison.

Uses base.yaml and approved development seeds only. This never changes or locks the
research protocol, and does not substitute for the full multi-family benchmark.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from aether.config import load_scenario
from aether.contracts import PolicyId, RunRecord
from aether.evaluation.benchmark import (
    RECALL_METRIC,
    RunFn,
    _aggregate,
    _compare,
    _write_csv,
    default_run_fn,
    unpack_run_result,
)
from aether.evaluation.matrix import performance_summary
from aether.evaluation.metrics import score_run
from aether.evaluation.protocol import file_sha256, load_protocol, read_seeds

POLICIES = (PolicyId.LARGEST_FIRST, PolicyId.ADAPTIVE_EIG, PolicyId.GREEDY_EIG)


def development_comparison(
    repo: Path,
    out_dir: Path,
    seeds: tuple[int, ...] = (1000,),
    *,
    run_fn: RunFn = default_run_fn,
) -> dict:
    """Score real runs and write evaluator CSV/CI artifacts plus measured timing.

    Every requested seed must belong to the protocol's development list. Measured
    complete-run elapsed times live in a separate, explicitly nondeterministic file.
    """
    repo, out_dir = repo.resolve(), out_dir.resolve()
    protocol_path = repo / "experiments/protocol.yaml"
    proto = load_protocol(protocol_path)
    approved = set(read_seeds(repo / proto.tuning_seeds))
    if not seeds or len(set(seeds)) != len(seeds) or not set(seeds) <= approved:
        raise ValueError("request unique, approved development seeds only")
    base = repo / "configs/base.yaml"
    rows, timings = [], []
    datasets: set[str] = set()  # the pinned plume dataset each run actually used (DATA-02)
    score_keys: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    config_hashes = {}
    for seed in seeds:
        bundle = load_scenario(base, seed=seed)
        config_hashes[str(seed)] = {
            "model": bundle.model.config_hash(),
            "truth": bundle.truth.config_hash(),
        }
        for policy in POLICIES:
            print(
                f"Running {policy.value}, development seed {seed}, configs/base.yaml…", flush=True
            )
            run_started = perf_counter()
            run, truth, performance = unpack_run_result(run_fn(bundle, policy, seed))
            elapsed_s = perf_counter() - run_started
            if run.policy_id is not policy or run.seed != seed or run.family != bundle.model.family:
                raise RuntimeError(f"runner mislabelled run {run.run_id}")
            # Round-trip the actual nested contract before publishing it.
            encoded = run.model_dump_json()
            RunRecord.model_validate_json(encoded)
            scores = score_run(run, truth, bundle.model)
            ref = getattr(run, "input_dataset", None)
            datasets.add(json.dumps(None if ref is None else ref.model_dump(mode="json"),
                                    sort_keys=True))  # fmt: skip
            if scores["plans_without_validation"] or scores["feasibility_checker_violations"]:
                raise RuntimeError(f"run {run.run_id} failed independent schedule validation")
            run_dir = out_dir / run.run_id
            run_dir.mkdir(exist_ok=True)
            (run_dir / "run.json").write_text(encoded + "\n", encoding="utf-8")
            for key in scores:
                if key not in score_keys:
                    score_keys.append(key)
            rows.append(
                {"family": run.family, "policy": policy.value, "seed": seed, "run_id": run.run_id}
                | scores
            )
            timings.append(
                {
                    "run_id": run.run_id,
                    "complete_run_elapsed_s": elapsed_s,
                    "performance": performance_summary(performance),
                }
            )
            print(
                f"{policy.value} seed {seed}: {elapsed_s:.3f} s, "
                f"Brier {scores['brier_active_state']:.6f}, "
                f"{scores['feasibility_checker_violations']} checker violations",
                flush=True,
            )

    _write_csv(
        out_dir / "benchmark-runs.csv", rows, ["family", "policy", "seed", "run_id", *score_keys]
    )
    _write_csv(
        out_dir / "benchmark-results.csv",
        _aggregate(rows, score_keys),
        [
            "family",
            "policy",
            "metric",
            "breakdown",
            "mean",
            "sd",
            "n_seeds",
            "n_defined",
            "n_undefined",
        ],
    )
    family = rows[0]["family"]
    comparisons = [
        _compare(
            rows,
            family,
            "adaptive_eig",
            other,
            metric,
            proto.analysis.resamples,
            proto.analysis.level,
            proto.protocol_version,
        )
        for other in ("largest_first", "greedy_eig")
        for metric in (proto.primary_metric, RECALL_METRIC)
    ]
    insufficient = len(seeds) < 10  # PRD UI-05 minimum display count.
    for comparison in comparisons:
        comparison["preliminary"] = True
        if comparison["n_pairs"] < 10:
            comparison["note"] = "insufficient samples (< 10 defined pairs); preliminary"
    report = {
        "label": "SIMULATED MISSION — offline development comparison",
        "protocol_version": proto.protocol_version,
        "protocol_sha256": file_sha256(protocol_path),
        "protocol_locked": proto.locked,
        "lock_tag": None,
        "base_config": "configs/base.yaml",
        "config_hashes": config_hashes,
        "input_datasets": [json.loads(d) for d in sorted(datasets)],
        "seeds": list(seeds),
        "n_seeds": len(seeds),
        "preliminary": True,
        "insufficient_samples": insufficient,
        "total_checker_violations": 0,
        "comparisons": comparisons,
        "holm_primary": {},
        "success_verdict": None,
        "note": (
            "Preliminary development results; "
            + ("insufficient samples; " if insufficient else "")
            + "single family only; research success criterion not evaluated."
        ),
    }
    (out_dir / "benchmark-confidence-intervals.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "development-timing.json").write_text(
        json.dumps(
            {
                "note": "Measured wall time; nondeterministic sidecar, not solver runtime.",
                "complete_comparison_elapsed_s": perf_counter() - started,
                "runs": timings,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output-dir", type=Path, default=Path("runs/development"))
    parser.add_argument(
        "--seeds", default="1000", help="comma-separated approved development seeds"
    )
    args = parser.parse_args()
    development_comparison(
        args.repo, args.output_dir, tuple(int(seed) for seed in args.seeds.split(","))
    )


if __name__ == "__main__":
    main()
