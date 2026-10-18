"""Discriminability gate G4.5 driver (EVL-08, PR-E06): reference policies on the tuning seeds.

Runs ``oracle`` (oracle-informed greedy reference; reads truth) and ``random_feasible`` for every
requested family on the protocol's tuning seeds, then applies the protocol rule

    mean(random - oracle Brier) > 2 * SD(random - oracle Brier)   (SD across seeds, not SE)

per family. Holdout seeds are refused outright: the gate is a pre-lock, tuning-only check.

Family scope (decision D9 in docs/validation-report.md): every registered protocol family is
evaluated and reported. The gate passes overall only when it passes in every family run, because a
family without reference-policy separation cannot support its share of the success criterion.

Writes ``gate.json`` (verdicts, capacity summaries, provenance), ``gate-seeds.csv`` (per-seed
paired values) and the reusable per-run records of ``matrix.run_matrix``. Never a holdout result
and never a policy comparison: reference policies are not competitors.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from aether.evaluation.matrix import execution_environment, family_bundle, run_matrix
from aether.evaluation.protocol import (
    ProtocolLockError,
    check_seed_access,
    file_sha256,
    load_protocol,
    read_seeds,
)
from aether.evaluation.stats import discriminability_gate

REFERENCE = ("oracle", "random_feasible")
CAPACITY_FIELDS = ("passes", "passes_per_72h", "acquisitions", "acquisitions_per_pass",
                   "capacity_to_demand_ratio")  # fmt: skip


def _summary(values: list[float | None]) -> dict:
    vals = [v for v in values if v is not None]
    if not vals:
        return {"n": 0, "mean": None, "min": None, "max": None}
    return {"n": len(vals), "mean": float(np.mean(vals)), "min": float(min(vals)),
            "max": float(max(vals))}  # fmt: skip


def gate_from_records(records: dict, families, seeds) -> dict:
    out = {}
    for family in families:
        oracle = [records[(family, "oracle", s)]["scores"]["brier_active_state"] for s in seeds]
        rand = [records[(family, "random_feasible", s)]["scores"]["brier_active_state"]
                for s in seeds]  # fmt: skip
        g = discriminability_gate(oracle, rand)
        caps = [records[(family, "random_feasible", s)]["capacity"] for s in seeds]
        violations = sum(int(records[(family, p, s)]["scores"]["feasibility_checker_violations"])
                         for p in REFERENCE for s in seeds)  # fmt: skip
        out[family] = {
            "passed": g.passed,
            "gap_mean_random_minus_oracle": g.gap,
            "sd_paired": g.sd_paired,
            "threshold_2sd": 2 * g.sd_paired,
            "se_paired": g.sd_paired / np.sqrt(g.n_seeds),
            "n_seeds": g.n_seeds,
            "seeds_where_oracle_better": int(
                sum(r > o for o, r in zip(oracle, rand, strict=False))
            ),
            "mean_brier": {
                "oracle": float(np.mean(oracle)),
                "random_feasible": float(np.mean(rand)),
            },
            "rule": g.rule,
            "capacity_random_feasible": {
                k: _summary([c[k] for c in caps]) for k in CAPACITY_FIELDS
            },  # fmt: skip
            "reference_checker_violations": violations,
        }
    return out


def run_gate(
    repo: Path,
    out_dir: Path,
    families=None,
    workers: int = 1,
    seeds_file: str | None = None,
    seed_subset: tuple[int, ...] | None = None,
    run_fn=None,
    synthetic_only: bool = False,
) -> dict:
    """``seed_subset`` (smoke checks only) must be drawn from the tuning list; reported as such."""
    repo, out_dir = repo.resolve(), out_dir.resolve()
    protocol_path = repo / "experiments/protocol.yaml"
    proto = load_protocol(protocol_path)
    seeds_path = repo / (seeds_file or proto.tuning_seeds)
    if check_seed_access(proto, protocol_path, seeds_path) is not None:
        raise ProtocolLockError("G4.5 runs on tuning seeds only, never holdout")
    seeds = read_seeds(seeds_path)
    if seed_subset is not None:
        if not set(seed_subset) <= set(seeds) or len(set(seed_subset)) != len(seed_subset):
            raise ValueError("seed_subset must be unique tuning seeds")
        seeds = tuple(seed_subset)
    families = tuple(families or proto.families)
    unknown = set(families) - set(proto.families) - {"h168_long_horizon"}
    if unknown:
        raise ValueError(f"unknown families {sorted(unknown)}")
    records = run_matrix(
        repo,
        proto.base_config,
        families,
        REFERENCE,
        seeds,
        out_dir,
        workers,
        run_fn=run_fn,
        synthetic_only=synthetic_only,
    )

    per_family = gate_from_records(records, families, seeds)
    with (out_dir / "gate-seeds.csv").open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(
            [
                "family",
                "seed",
                "oracle_brier",
                "random_brier",
                "random_minus_oracle",
                "passes",
                "acquisitions",
                "acquisitions_per_pass",
                "capacity_to_demand_ratio",
            ]
        )
        for f in families:
            for s in seeds:
                o = records[(f, "oracle", s)]["scores"]["brier_active_state"]
                r = records[(f, "random_feasible", s)]
                c = r["capacity"]
                w.writerow([f, s, o, r["scores"]["brier_active_state"],
                            r["scores"]["brier_active_state"] - o, c["passes"],
                            c["acquisitions"], c["acquisitions_per_pass"],
                            c["capacity_to_demand_ratio"]])  # fmt: skip
    datasets = sorted({json.dumps(r["input_dataset"], sort_keys=True) for r in records.values()})
    report = {
        "label": "SIMULATED MISSION — G4.5 discriminability gate (tuning seeds; reference "
        "policies only; not a policy comparison)",
        "reference_note": "oracle = oracle-informed greedy reference that reads truth; not a "
        "proven upper bound",
        "family_scope_rule": "gate passes only if it passes in every family evaluated (D9)",
        "families": list(families),
        "overall_passed": all(v["passed"] for v in per_family.values()),
        "per_family": per_family,
        "protocol_sha256": file_sha256(protocol_path),
        "protocol_locked": proto.locked,
        "seeds_file": str(seeds_path.relative_to(repo)),
        "seeds_sha256": file_sha256(seeds_path),
        "seeds": list(seeds),
        "seed_subset_only": seed_subset is not None,
        "config_hashes": {
            f: {
                "model": (
                    b := family_bundle(
                        repo, proto.base_config, f, seeds[0], synthetic_only=synthetic_only
                    )
                ).model.config_hash(),
                "truth": b.truth.config_hash(),
                "seed_for_hash": seeds[0],
            }
            for f in families
        },  # fmt: skip
        "synthetic_only": synthetic_only,
        "input_datasets": [json.loads(d) for d in datasets],
        "environment": execution_environment(repo),
    }
    (out_dir / "gate.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    ap.add_argument("--output-dir", type=Path, default=Path("runs/gate"))
    ap.add_argument("--families", default="", help="comma-separated; default all protocol families")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--seeds-file", default=None, help="repo-relative; must be the tuning list")
    ap.add_argument("--seed-subset", default="", help="smoke only: comma-separated tuning seeds")
    ap.add_argument("--synthetic-only", action="store_true", help="ignore the plume dataset")
    args = ap.parse_args()
    fams = [f for f in args.families.split(",") if f] or None
    subset = tuple(int(x) for x in args.seed_subset.split(",") if x) or None
    report = run_gate(
        args.repo,
        args.output_dir,
        fams,
        args.workers,
        args.seeds_file,
        subset,
        synthetic_only=args.synthetic_only,
    )
    for f, v in report["per_family"].items():
        print(
            f"{f}: {'PASS' if v['passed'] else 'FAIL'} gap {v['gap_mean_random_minus_oracle']:.4f}"
            f" vs 2SD {v['threshold_2sd']:.4f} (n={v['n_seeds']})"
        )
    print("overall:", "PASS" if report["overall_passed"] else "FAIL")


if __name__ == "__main__":
    main()
