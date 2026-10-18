"""Build deterministic base-scenario windows for independent Agent 5 review.

Run from ``backend`` after installing the project extras:
``python ../scripts/build_orbit_candidate.py``.
This writes a candidate fixture, not a golden test oracle.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import timedelta
from importlib.metadata import version
from pathlib import Path
from statistics import median

from aether.config import load_scenario
from aether.ingestion import build_sources
from aether.orbit import generate_windows, slew_time_s

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "base.yaml"
OUTPUT_PATH = ROOT / "data" / "fixtures" / "windows_base_candidate.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    bundle = load_scenario(CONFIG_PATH)
    cfg = bundle.model
    sources = build_sources(cfg, (), seed=cfg.random_seed)
    start_utc = cfg.simulation_epoch_utc
    end_utc = start_utc + timedelta(hours=cfg.horizon_hours)
    windows = generate_windows(cfg, sources, start_utc, end_utc)

    source_json = json.dumps(
        [source.model_dump(mode="json") for source in sources],
        sort_keys=True,
        separators=(",", ":"),
    )
    grouped = defaultdict(list)
    for window in windows:
        if window.feasible:
            grouped[(window.spacecraft_id, window.pass_id)].append(window)
    available_targets = [len({w.source_id for w in group}) for group in grouped.values()]
    capacity_proxy = []
    for (spacecraft_id, _), group in grouped.items():
        profile = cfg.spacecraft[spacecraft_id]
        representatives = [
            min(window.options, key=lambda option: option.off_nadir_deg) for window in group
        ]
        representatives.sort(key=lambda option: option.start_utc)
        transition_s = [
            slew_time_s(left, right, profile.attitude)
            for left, right in zip(representatives, representatives[1:], strict=False)
        ]
        median_cycle_s = cfg.sensors[profile.sensor_ids[0]].exposure_seconds + median(
            transition_s or [profile.attitude.settle_seconds]
        )
        dwell_s = (max(w.end_utc for w in group) - min(w.start_utc for w in group)).total_seconds()
        capacity_proxy.append(int(dwell_s // median_cycle_s))

    eop_manifest = ROOT / "data" / "eop" / "manifest.json"
    ephemeris_manifest = ROOT / "data" / "ephemeris" / "manifest.json"
    artifact = {
        "artifact_status": "CANDIDATE_PENDING_AGENT5_REVIEW",
        "scenario_id": cfg.scenario_id,
        "model_config_hash": cfg.config_hash(),
        "config_file_sha256": _sha256(CONFIG_PATH),
        "source_count": len(sources),
        "source_seed": cfg.random_seed,
        "source_set_sha256": hashlib.sha256(source_json.encode()).hexdigest(),
        "sources": [source.model_dump(mode="json") for source in sources],
        "start_utc": start_utc.isoformat(),
        "end_utc": end_utc.isoformat(),
        "input_hashes": {
            "de421_sha256": json.loads(ephemeris_manifest.read_text())["sha256"],
            "iers_finals2000a_sha256": json.loads(eop_manifest.read_text())["sha256"],
        },
        "software": {name: version(name) for name in ("aether", "skyfield", "sgp4")},
        "counts": {
            "windows_total": len(windows),
            "windows_feasible": sum(w.feasible for w in windows),
            "spacecraft_regional_passes": len(grouped),
            "feasible_source_windows_per_pass_min": min(available_targets, default=0),
            "feasible_source_windows_per_pass_median": (
                sorted(available_targets)[len(available_targets) // 2] if available_targets else 0
            ),
            "feasible_source_windows_per_pass_max": max(available_targets, default=0),
            "median_capacity_proxy_acquisitions_per_pass": (
                sorted(capacity_proxy)[len(capacity_proxy) // 2] if capacity_proxy else 0
            ),
            "max_capacity_proxy_acquisitions_per_pass": max(capacity_proxy, default=0),
        },
        "windows": [window.model_dump(mode="json") for window in windows],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(json.dumps(artifact["counts"], indent=2, sort_keys=True))
    print(f"candidate: {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
