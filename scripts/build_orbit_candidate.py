"""Build deterministic base-scenario windows and capacity evidence.

Run from ``backend`` after installing the project extras:
``python ../scripts/build_orbit_candidate.py``.
This writes a candidate fixture, not a golden test oracle. Codex-3 owns independent review and
promotion to ``backend/tests/golden/windows_base.json``.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import timedelta
from importlib.metadata import version
from itertools import pairwise
from pathlib import Path
from statistics import median

from aether.config import load_scenario
from aether.contracts.enums import PolicyId, SolverStatus
from aether.contracts.models import CandidateUtility, ObservationWindow, Source
from aether.ingestion import build_sources
from aether.orbit import generate_windows, slew_time_s
from aether.planning.checker import check_schedule
from aether.planning.cpsat import solve_schedule

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "base.yaml"
OUTPUT_PATH = ROOT / "data" / "fixtures" / "windows_base_candidate.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _schedule_pass_capacity(windows, profile, cfg, sources=None) -> dict:
    """Maximize scheduled acquisition count for one geometric pass with production constraints.

    The equal integer objective is a counting objective, not an information-gain estimate. The
    production scheduler still enforces option membership, slew, no-overlap, source visits,
    per-orbit count, storage, and energy constraints.
    """
    utilities = {
        window.id: CandidateUtility(
            window_id=window.id,
            plan_revision=0,
            expected_info_gain_bits=cfg.planner.min_utility_bits,
            decision_relevance=0.0,
            latency_s=0.0,
            resource_cost=0.0,
            p_valid_forecast=0.0,
            utility=cfg.planner.min_utility_bits,
            integer_utility=cfg.planner.utility_integer_scale,
        )
        for window in windows
    }
    plan, _ = solve_schedule(
        windows,
        utilities,
        {profile.id: profile},
        cfg.planner,
        run_id="orbit-capacity-diagnostic",
        revision=0,
        cause="orbit_capacity_diagnostic",
        policy_id=PolicyId.ADAPTIVE_EIG,
        random_seed=cfg.random_seed,
    )
    if plan.solver_status is not SolverStatus.OPTIMAL:
        raise RuntimeError(
            f"capacity solve for {windows[0].pass_id} ended with {plan.solver_status.value}"
        )
    result = {
        "spacecraft_id": windows[0].spacecraft_id,
        "pass_id": windows[0].pass_id,
        "orbit_number": windows[0].orbit_number,
        "feasible_source_windows": len(windows),
        "feasible_options": sum(len(window.options) for window in windows),
        "scheduled_acquisitions": len(plan.selections),
        "selected_option_ids": [selection.option_id for selection in plan.selections],
        "solver_status": plan.solver_status.value,
    }
    if sources is not None:
        validation = check_schedule(
            plan,
            windows,
            sources,
            {profile.id: profile},
            cfg.sensors[profile.sensor_ids[0]],
            cfg,
        )
        result["checker_ok"] = validation.ok
        result["checker_violations"] = [
            violation.model_dump(mode="json") for violation in validation.violations
        ]
    return result


def build_candidate(
    cfg,
    sources,
    *,
    source_input=None,
    output_path=OUTPUT_PATH,
    windows_override=None,
    window_source_sha256=None,
) -> dict:
    """Generate and write an orbit candidate for a supplied, already-pinned source set."""
    source_input = source_input or {
        "mode": "synthetic_uniform_fill",
        "uniform_fill_count": len(sources),
        "plume_record_count": 0,
    }
    start_utc = cfg.simulation_epoch_utc
    end_utc = start_utc + timedelta(hours=cfg.horizon_hours)
    windows = (
        list(windows_override)
        if windows_override is not None
        else generate_windows(cfg, sources, start_utc, end_utc)
    )

    source_json = json.dumps(
        [source.model_dump(mode="json") for source in sources],
        sort_keys=True,
        separators=(",", ":"),
    )
    grouped = defaultdict(list)
    for window in windows:
        if window.feasible:
            grouped[(window.spacecraft_id, window.pass_id)].append(window)
    available_targets = [
        len({w.source_id for w in group}) for group in grouped.values()
    ]
    capacity_passes = [
        _schedule_pass_capacity(
            sorted(group, key=lambda window: window.id),
            cfg.spacecraft[spacecraft_id],
            cfg,
            sources,
        )
        for (spacecraft_id, _pass_id), group in sorted(grouped.items())
    ]
    scheduled_per_pass = [item["scheduled_acquisitions"] for item in capacity_passes]
    capacity_proxy = []
    for (spacecraft_id, _), group in grouped.items():
        profile = cfg.spacecraft[spacecraft_id]
        representatives = [
            min(window.options, key=lambda option: option.off_nadir_deg)
            for window in group
        ]
        representatives.sort(key=lambda option: option.start_utc)
        transition_s = [
            slew_time_s(left, right, profile.attitude)
            for left, right in pairwise(representatives)
        ]
        median_cycle_s = cfg.sensors[profile.sensor_ids[0]].exposure_seconds + median(
            transition_s or [profile.attitude.settle_seconds]
        )
        dwell_s = (
            max(w.end_utc for w in group) - min(w.start_utc for w in group)
        ).total_seconds()
        capacity_proxy.append(int(dwell_s // median_cycle_s))

    eop_manifest = ROOT / "data" / "eop" / "manifest.json"
    ephemeris_manifest = ROOT / "data" / "ephemeris" / "manifest.json"
    artifact = {
        "artifact_status": "CANDIDATE_NOT_GOLDEN",
        "scenario_id": cfg.scenario_id,
        "model_config_hash": cfg.config_hash(),
        "config_file_sha256": _sha256(CONFIG_PATH),
        "source_count": len(sources),
        "source_seed": cfg.random_seed
        if source_input["mode"] == "synthetic_uniform_fill"
        else None,
        "source_input": source_input,
        "source_set_sha256": hashlib.sha256(source_json.encode()).hexdigest(),
        "sources": [source.model_dump(mode="json") for source in sources],
        "start_utc": start_utc.isoformat(),
        "end_utc": end_utc.isoformat(),
        "input_hashes": {
            "de421_sha256": json.loads(ephemeris_manifest.read_text())["sha256"],
            "iers_finals2000a_sha256": json.loads(eop_manifest.read_text())["sha256"],
        },
        "code_hashes": {
            "orbit_module_sha256": _sha256(
                ROOT / "backend" / "aether" / "orbit" / "__init__.py"
            ),
            "capacity_builder_sha256": _sha256(Path(__file__).resolve()),
            "planner_solver_sha256": _sha256(
                ROOT / "backend" / "aether" / "planning" / "cpsat.py"
            ),
            "schedule_checker_sha256": _sha256(
                ROOT / "backend" / "aether" / "planning" / "checker.py"
            ),
        },
        "software": {name: version(name) for name in ("aether", "skyfield", "sgp4")},
        "counts": {
            "windows_total": len(windows),
            "windows_feasible": sum(w.feasible for w in windows),
            "spacecraft_regional_passes": len(grouped),
            "feasible_source_windows_per_pass_min": min(available_targets, default=0),
            "feasible_source_windows_per_pass_median": median(available_targets)
            if available_targets
            else 0,
            "feasible_source_windows_per_pass_max": max(available_targets, default=0),
            "median_capacity_proxy_acquisitions_per_pass": median(capacity_proxy)
            if capacity_proxy
            else 0,
            "max_capacity_proxy_acquisitions_per_pass": max(capacity_proxy, default=0),
            "scheduled_acquisitions_per_pass_min": min(scheduled_per_pass, default=0),
            "scheduled_acquisitions_per_pass_median": median(scheduled_per_pass)
            if scheduled_per_pass
            else 0,
            "scheduled_acquisitions_per_pass_max": max(scheduled_per_pass, default=0),
            "g1f_pass_count_threshold_met": len(grouped) >= 5,
            "g1f_capacity_threshold_met": min(scheduled_per_pass, default=0) >= 4,
            "g1f_checker_zero_violations": all(
                item.get("checker_ok", False) for item in capacity_passes
            ),
        },
        "capacity_method": {
            "status": "PER_PASS_CAPACITY_DIAGNOSTIC",
            "objective": "maximize scheduled acquisition count independently per geometric pass",
            "scheduler": "aether.planning.cpsat.solve_schedule",
            "constraints": [
                "one option per window",
                "slew and no-overlap",
                "maximum visits per source per solve",
                "maximum acquisitions per orbit",
                "storage",
                "energy",
            ],
            "cross_pass_resource_coupling": (
                "not modeled; each pass is an independent capacity solve"
            ),
            "policy_performance_claim": False,
            "independent_checker_review": (
                "tracked separately; artifact does not self-certify independent verification"
            ),
        },
        "capacity_passes": capacity_passes,
        "windows": [window.model_dump(mode="json") for window in windows],
        "window_provenance": {
            "mode": "reused_existing_candidate"
            if windows_override is not None
            else "generated_from_pinned_ephemeris",
            "source_artifact_sha256": window_source_sha256,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(json.dumps(artifact["counts"], indent=2, sort_keys=True))
    print(f"candidate: {output_path.relative_to(ROOT)}")
    return artifact


def refresh_candidate_capacity(path: Path) -> dict:
    """Recompute scheduling evidence from a candidate's pinned serialized windows."""
    path = path.resolve()
    previous_sha256 = _sha256(path)
    existing = json.loads(path.read_text())
    cfg = load_scenario(CONFIG_PATH).model
    sources = [Source.model_validate(item) for item in existing["sources"]]
    windows = [ObservationWindow.model_validate(item) for item in existing["windows"]]
    return build_candidate(
        cfg,
        sources,
        source_input=existing.get("source_input"),
        output_path=path,
        windows_override=windows,
        window_source_sha256=previous_sha256,
    )


def main() -> None:
    cfg = load_scenario(CONFIG_PATH).model
    sources = build_sources(cfg, (), seed=cfg.random_seed)
    build_candidate(cfg, sources)


if __name__ == "__main__":
    main()
