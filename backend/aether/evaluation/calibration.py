"""SCI-10 calibration analysis on well-specified (m0) development runs.

Input: per-run calibration points from ``matrix.calibration_points``
``[hours_from_t0, source_id, p_active, z_true, ci_lo_kg_h, ci_hi_kg_h, true_Q_kg_h]``, grouped by
seed. Points within one run are strongly correlated (same sources at 12 times), so every interval
here comes from a **seed-cluster bootstrap**: whole seeds are resampled, never individual points.

Acceptance (Work_Plan SCI-10): pooled 90% flux-interval coverage in [0.85, 0.95], and the
reliability curve within sampling error, meaning each populated bin's 95% cluster-bootstrap CI of
(observed frequency - mean forecast) contains 0. With 10 bins, about one bin in two runs can miss
by chance at 95%, so the report also lists the calibration-in-the-large CI.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from aether.rng import keyed_rng

COVERAGE_BAND = (0.85, 0.95)  # Work_Plan SCI-10
RELIABILITY_BINS = 10  # same equal-width bins as ECE (PR-E09)


def _arrays(points: Sequence[Sequence]) -> dict[str, np.ndarray]:
    a = np.asarray([(p[0], p[2], p[3], p[4], p[5], p[6]) for p in points], dtype=float)
    return {"t": a[:, 0], "p": a[:, 1], "z": a[:, 2], "lo": a[:, 3], "hi": a[:, 4], "q": a[:, 5]}


def _cluster_ci(per_seed_num, per_seed_den, rng, resamples, level=0.95):
    num, den = np.asarray(per_seed_num, float), np.asarray(per_seed_den, float)
    idx = rng.integers(0, len(num), size=(resamples, len(num)))
    d = den[idx].sum(axis=1)
    stats = np.where(d > 0, num[idx].sum(axis=1) / np.where(d > 0, d, 1), np.nan)
    stats = stats[np.isfinite(stats)]
    a = (1 - level) / 2
    return float(np.quantile(stats, a)), float(np.quantile(stats, 1 - a))


def calibration_report(
    points_by_seed: Mapping[int, Sequence[Sequence]],
    resamples: int = 2000,
    seed: int = 0,
    label: str = "",
) -> dict:
    seeds = sorted(points_by_seed)
    if len(seeds) < 2:
        raise ValueError("calibration needs at least 2 seeds")
    arr = {s: _arrays(points_by_seed[s]) for s in seeds}
    rng = keyed_rng(seed, "bootstrap", "calibration", label)

    # Flux interval coverage, pooled and at the final evaluation time only.
    def cover(a, mask=None):
        hit = (a["lo"] <= a["q"]) & (a["q"] <= a["hi"])
        m = np.ones_like(hit) if mask is None else mask
        return float(hit[m].sum()), float(m.sum())

    pooled = [cover(arr[s]) for s in seeds]
    final = [cover(arr[s], arr[s]["t"] == arr[s]["t"].max()) for s in seeds]
    coverage = {}
    for name, rows in (("all_points", pooled), ("final_time", final)):
        num, den = zip(*rows, strict=False)
        value = sum(num) / sum(den)
        coverage[name] = {
            "coverage": value,
            "ci95_seed_cluster": _cluster_ci(num, den, rng, resamples),
            "per_seed": {s: n / d for s, n, d in zip(seeds, num, den, strict=False)},
            "n_points": int(sum(den)),
        }
    coverage["band"] = list(COVERAGE_BAND)
    coverage["within_band"] = (
        COVERAGE_BAND[0] <= coverage["all_points"]["coverage"] <= COVERAGE_BAND[1]
    )

    # Reliability: per bin, observed frequency minus mean forecast, cluster-bootstrapped.
    bins = []
    for b in range(RELIABILITY_BINS):
        z_sum, p_sum, n = [], [], []
        for s in seeds:
            a = arr[s]
            idx = np.minimum((a["p"] * RELIABILITY_BINS).astype(int), RELIABILITY_BINS - 1)
            m = idx == b
            z_sum.append(a["z"][m].sum())
            p_sum.append(a["p"][m].sum())
            n.append(m.sum())
        if sum(n) == 0:
            bins.append({"bin": b, "n": 0})
            continue
        resid = np.asarray(z_sum) - np.asarray(p_sum)
        lo, hi = _cluster_ci(resid, n, rng, resamples)
        bins.append({
            "bin": b, "range": [b / RELIABILITY_BINS, (b + 1) / RELIABILITY_BINS],
            "n": int(sum(n)), "n_seeds_populated": int(sum(x > 0 for x in n)),
            "mean_forecast": float(sum(p_sum) / sum(n)),
            "observed_freq": float(sum(z_sum) / sum(n)),
            "residual_ci95": [lo, hi], "contains_zero": lo <= 0.0 <= hi,
        })  # fmt: skip
    resid_all = [float((arr[s]["z"] - arr[s]["p"]).sum()) for s in seeds]
    n_all = [len(arr[s]["p"]) for s in seeds]
    populated = [b for b in bins if b["n"]]
    return {
        "label": label,
        "seeds": seeds,
        "n_seeds": len(seeds),
        "bootstrap": {"kind": "seed-cluster percentile", "resamples": resamples, "level": 0.95},
        "flux_interval_coverage_90": coverage,
        "reliability": bins,
        "bins_ci_excluding_zero": [b["bin"] for b in populated if not b["contains_zero"]],
        "calibration_in_the_large": {
            "mean_z_minus_p": sum(resid_all) / sum(n_all),
            "ci95_seed_cluster": _cluster_ci(resid_all, n_all, rng, resamples),
        },
    }


def main() -> None:
    import argparse
    import json
    from pathlib import Path

    from aether.evaluation.matrix import execution_environment, run_matrix
    from aether.evaluation.protocol import file_sha256, load_protocol, read_seeds

    ap = argparse.ArgumentParser(description="SCI-10 m0 calibration on tuning seeds")
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    ap.add_argument("--output-dir", type=Path, default=Path("runs/dev"))
    ap.add_argument("--policies", default="adaptive_eig,random_feasible")
    ap.add_argument("--n-seeds", type=int, default=5, help="first N tuning seeds (SCI-10: 5)")
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()
    repo = args.repo.resolve()
    proto = load_protocol(repo / "experiments/protocol.yaml")
    seeds_path = repo / proto.tuning_seeds
    seeds = read_seeds(seeds_path)[: args.n_seeds]
    policies = [p for p in args.policies.split(",") if p]
    family = "m0_well_specified"
    records = run_matrix(repo, proto.base_config, [family], policies, seeds, args.output_dir,
                         args.workers)  # fmt: skip
    report = {
        "label": "SIMULATED MISSION — SCI-10 calibration, m0, tuning seeds (development only)",
        "family": family,
        "seeds_sha256": file_sha256(seeds_path),
        "environment": execution_environment(repo),
        "input_datasets": sorted(
            {json.dumps(r["input_dataset"], sort_keys=True) for r in records.values()}
        ),
        "by_policy": {
            p: calibration_report(
                {s: records[(family, p, s)]["calibration"] for s in seeds},
                label=f"{family}|{p}",
            )
            for p in policies
        },
    }
    out = args.output_dir / "calibration-m0.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    for p, r in report["by_policy"].items():
        cov = r["flux_interval_coverage_90"]["all_points"]
        print(
            f"{p}: coverage {cov['coverage']:.3f} CI {cov['ci95_seed_cluster']}, bins off "
            f"{r['bins_ci_excluding_zero']}, CITL {r['calibration_in_the_large']}"
        )


if __name__ == "__main__":
    main()
