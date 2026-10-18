"""SCI-08: descriptive comparison of downloaded EMIT V002 Permian plume rates with the flux prior.

Read-only analysis of the local metadata JSONs (never the rasters, never a run input). Output is
``experiments/results/sci08_emit_flux.json``. The script is deterministic: files are processed in
sorted order and no random numbers are drawn.

What this can and cannot show (see docs/model-card-source-state.md, SCI-08):
- EMIT plume complexes exist only where something was detected AND the rate passed the provider's
  quantification screen, so the rates are a detection- and screening-selected sample. They cannot
  validate the population prior PR-P10, which includes sources that are rarely or never detected.
- Absent plume rows say nothing about inactivity (AGENTS rule 3). No persistence is inferred.
- The provider's "Emissions Rate Estimate Uncertainty (kg/hr)" is reported as a ratio to the rate
  only; its statistical meaning (1-sigma, interval half-width, ...) is not defined in the public
  ATBD v0.2 / User Guide v02 (April 2025), so it stays UNKNOWN.

Usage: python experiments/sci08_emit_flux.py <raw_dir> [--config configs/base.yaml]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import yaml
from scipy import stats

RATE = "Emissions Rate Estimate (kg/hr)"
UNC = "Emissions Rate Estimate Uncertainty (kg/hr)"
QUANTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int | float):
        return float(v) if math.isfinite(v) else None
    return None  # "NA" and any other string stays missing


def load_region_records(raw_dir: Path, bbox) -> tuple[list[dict], dict]:
    w, s, e, n = bbox
    out, counts = [], {"files": 0, "features": 0, "in_bbox": 0}
    for path in sorted(raw_dir.glob("*.json")):
        doc = json.loads(path.read_text())
        counts["files"] += 1
        for feat in doc.get("features", []):
            counts["features"] += 1
            p = feat["properties"]
            lat, lon = (
                p.get("Latitude of max concentration"),
                p.get("Longitude of max concentration"),
            )
            if not (isinstance(lat, int | float) and isinstance(lon, int | float)):
                continue
            if not (w <= lon <= e and s <= lat <= n):
                continue
            counts["in_bbox"] += 1
            out.append({
                "file": path.name,
                "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "plume_id": p.get("Plume ID"),
                "utc": p.get("UTC Time Observed"),
                "lat": lat, "lon": lon,
                "rate_kg_h": _num(p.get(RATE)),
                "rate_raw": p.get(RATE),
                "unc_kg_h": _num(p.get(UNC)),
                "wind_m_s": _num(p.get("Wind Speed (m/s)")),
                "wind_source": p.get("Wind Speed Source"),
                "fetch_m": _num(p.get("Fetch Length (m)")),
                "max_ppm_m": _num(p.get("Max Plume Concentration (ppm m)")),
            })  # fmt: skip
    return out, counts


def truncated_lognormal(median, sigma_ln, lo, hi):
    mu = math.log(median)
    a, b = (math.log(lo) - mu) / sigma_ln, (math.log(hi) - mu) / sigma_ln
    return stats.truncnorm(a, b, loc=mu, scale=sigma_ln)  # distribution of ln Q


def _q(x, qs=QUANTILES):
    return {f"q{int(q * 100):02d}": float(np.quantile(x, q)) for q in qs}


def analyse(records: list[dict], prior_cfg: dict) -> dict:
    ids = [r["plume_id"] for r in records]
    rates = np.array([r["rate_kg_h"] for r in records if r["rate_kg_h"] is not None])
    with_rate = [r for r in records if r["rate_kg_h"] is not None]
    missing = [r for r in records if r["rate_kg_h"] is None]
    prior = truncated_lognormal(prior_cfg["median_kg_h"], prior_cfg["sigma_ln"],
                                prior_cfg["min_kg_h"], prior_cfg["max_kg_h"])  # fmt: skip
    ln = np.log(rates)
    rel_unc = np.array([r["unc_kg_h"] / r["rate_kg_h"] for r in with_rate
                        if r["unc_kg_h"] is not None and r["rate_kg_h"] > 0])  # fmt: skip
    ks = stats.kstest(ln, prior.cdf)
    years = sorted({r["utc"][:4] for r in records if r["utc"]})
    return {
        "n_records_in_bbox": len(records),
        "n_unique_plume_ids": len(set(ids)),
        "n_numeric_rate": len(with_rate),
        "n_missing_rate": len(missing),
        "missing_rate_raw_values": sorted({str(r["rate_raw"]) for r in missing}),
        "missing_rate_with_numeric_wind": sum(
            r["wind_m_s"] is not None for r in missing
        ),
        "numeric_rate_with_numeric_wind": sum(
            r["wind_m_s"] is not None for r in with_rate
        ),
        "max_ppm_m_median": {
            "numeric_rate": float(
                np.median([r["max_ppm_m"] for r in with_rate if r["max_ppm_m"]])
            ),
            "missing_rate": float(
                np.median([r["max_ppm_m"] for r in missing if r["max_ppm_m"]])
            ),
        },
        "wind_sources": sorted({str(r["wind_source"]) for r in with_rate}),
        "observation_years": years,
        "observation_utc_range": [
            min(r["utc"] for r in records),
            max(r["utc"] for r in records),
        ],
        "rate_kg_h": {
            "min": float(rates.min()),
            "max": float(rates.max()),
            "geometric_mean": float(math.exp(ln.mean())),
            "sd_ln": float(ln.std(ddof=1)),
            **_q(rates),
        },  # fmt: skip
        "prior_PR_P10_kg_h": {
            "spec": prior_cfg,
            **{
                k: float(math.exp(prior.ppf(q)))
                for k, q in ((f"q{int(q * 100):02d}", q) for q in QUANTILES)
            },
            "sd_ln_truncated": float(prior.std()),
        },  # fmt: skip
        "share_emit_rates_below_prior_median": float(
            np.mean(rates < prior_cfg["median_kg_h"])
        ),
        "share_emit_rates_outside_prior_support": float(
            np.mean((rates < prior_cfg["min_kg_h"]) | (rates > prior_cfg["max_kg_h"]))
        ),
        "prior_mass_below_min_emit_rate": float(prior.cdf(math.log(rates.min()))),
        "ks_ln_rate_vs_prior": {
            "statistic": float(ks.statistic),
            "p_value": float(ks.pvalue),
            "note": "descriptive only: sample is detection-selected, not iid "
            "from the source population",
        },  # fmt: skip
        "relative_uncertainty_unc_over_rate": {"n": int(rel_unc.size), **_q(rel_unc)}
        if rel_unc.size
        else {"n": 0},
        "uncertainty_kind": "UNKNOWN",
        "uncertainty_kind_reason": "not defined in public EMIT GHG ATBD v0.2 (JPL D-107866, Apr "
        "2025) or L2B GHG User Guide draft v02 (JPL D-107867, Apr 2025)",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("raw_dir", type=Path)
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    repo = args.repo.resolve()
    base = yaml.safe_load((repo / "configs/base.yaml").read_text())
    region = yaml.safe_load((repo / "configs" / base["region_file"]).read_text())
    bbox = region.get("bbox_wgs84") or region.get("bbox")
    records, counts = load_region_records(args.raw_dir, bbox)
    result = {
        "label": "Historical EMIT V002 plume metadata (REAL_OBSERVATION context; 2022-2025). "
                 "Descriptive comparison only; never a run input.",
        "raw_dir": str(args.raw_dir.resolve().relative_to(repo))
        if args.raw_dir.resolve().is_relative_to(repo)
        else str(args.raw_dir),
        "region_bbox_wgs84": bbox,
        "inventory": counts,
        "analysis": analyse(records, base["sources"]["flux_prior"]),
        "records": [{k: r[k] for k in ("plume_id", "utc", "lat", "lon", "rate_kg_h", "unc_kg_h",
                                        "wind_m_s", "file", "file_sha256")} for r in records],
    }  # fmt: skip
    out = args.out or repo / "experiments/results/sci08_emit_flux.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps(result["analysis"], indent=1))


if __name__ == "__main__":
    main()
