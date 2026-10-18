"""Build a deterministic, checker-validated acquisition witness for each orbital pass.

This script does not call a planner or solver. It inserts feasible windows chronologically,
trying their discrete options in start-time order. A reported count is a feasible lower bound,
not a maximum-capacity claim. The windows artifact must be generated from the same source set
and configuration used for the scenario being checked.

Run from the repository root after installing the backend extras::

    python scripts/feasibility/capacity_witness.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from aether.config import ScenarioConfig, load_scenario
from aether.contracts.enums import PolicyId, SolverStatus
from aether.contracts.models import ObservationWindow, Plan, Selection, Source
from aether.planning.checker import check_schedule


def _plan_for_pass(
    pass_id: str,
    created_at_utc,
    candidate_window_ids: tuple[str, ...],
    selections: tuple[Selection, ...],
) -> Plan:
    return Plan(
        run_id=f"capacity-witness:{pass_id}",
        policy_id=PolicyId.FIRST_FEASIBLE,
        revision=0,
        created_at_sim_utc=created_at_utc,
        cause="independent capacity witness",
        objective_weights={},
        candidate_window_ids=candidate_window_ids,
        selections=selections,
        solver_status=SolverStatus.HEURISTIC,
        objective_value=None,
        best_bound=None,
        runtime_s=None,
    )


def _measure_pass(
    pass_id: str,
    windows: tuple[ObservationWindow, ...],
    sources: tuple[Source, ...],
    scenario: ScenarioConfig,
) -> dict[str, Any]:
    feasible_windows = tuple(window for window in windows if window.feasible)
    if not feasible_windows:
        return {
            "pass_id": pass_id,
            "spacecraft_ids": sorted({window.spacecraft_id for window in windows}),
            "orbit_numbers": sorted({window.orbit_number for window in windows}),
            "feasible_window_count": 0,
            "selected_acquisitions_lower_bound": 0,
            "selected_option_ids": [],
            "checker_ok": True,
            "rejected_candidate_rules": {},
        }

    sensor_ids = {window.sensor_id for window in feasible_windows}
    if len(sensor_ids) != 1:
        raise ValueError(f"pass {pass_id} has multiple sensor profiles: {sorted(sensor_ids)}")
    sensor_id = next(iter(sensor_ids))
    sensor = scenario.sensors.get(sensor_id)
    if sensor is None:
        raise ValueError(f"pass {pass_id} references unknown sensor {sensor_id}")

    candidate_window_ids = tuple(sorted(window.id for window in feasible_windows))
    created_at_utc = min(window.start_utc for window in feasible_windows)
    selected: list[Selection] = []
    selected_window_ids: set[str] = set()
    rejected_rules: Counter[str] = Counter()

    ordered_windows = sorted(
        feasible_windows,
        key=lambda window: (
            min(option.start_utc for option in window.options),
            window.source_id,
            window.id,
        ),
    )
    for window in ordered_windows:
        if window.id in selected_window_ids:
            continue
        for option in sorted(window.options, key=lambda item: (item.start_utc, item.option_id)):
            selection = Selection(window_id=window.id, option_id=option.option_id)
            proposed = _plan_for_pass(
                pass_id,
                created_at_utc,
                candidate_window_ids,
                (*selected, selection),
            )
            report = check_schedule(
                proposed,
                windows,
                sources,
                scenario.spacecraft,
                sensor,
                scenario,
            )
            if report.ok:
                selected.append(selection)
                selected_window_ids.add(window.id)
                break
            rejected_rules.update(violation.rule for violation in report.violations)

    final_plan = _plan_for_pass(pass_id, created_at_utc, candidate_window_ids, tuple(selected))
    final_report = check_schedule(
        final_plan,
        windows,
        sources,
        scenario.spacecraft,
        sensor,
        scenario,
    )
    if not final_report.ok:
        raise RuntimeError(
            f"capacity witness for pass {pass_id} failed independent validation: "
            f"{final_report.violations}"
        )
    return {
        "pass_id": pass_id,
        "spacecraft_ids": sorted({window.spacecraft_id for window in windows}),
        "orbit_numbers": sorted({window.orbit_number for window in windows}),
        "feasible_window_count": len(feasible_windows),
        "selected_acquisitions_lower_bound": len(selected),
        "selected_option_ids": [selection.option_id for selection in selected],
        "checker_ok": final_report.ok,
        "checker_violations": [
            violation.model_dump(mode="json") for violation in final_report.violations
        ],
        "rejected_candidate_rules": dict(sorted(rejected_rules.items())),
    }


def build_capacity_report(
    windows_path: Path,
    config_path: Path,
    *,
    repo_root: Path,
) -> dict[str, Any]:
    """Load one windows artifact and report independently checked lower bounds by pass."""
    raw_bytes = windows_path.read_bytes()
    artifact = json.loads(raw_bytes)
    scenario = load_scenario(config_path).model
    recorded_config_hash = artifact.get("model_config_hash")
    actual_config_hash = scenario.config_hash()
    if recorded_config_hash != actual_config_hash:
        raise ValueError(
            "windows artifact config hash differs from the supplied scenario: "
            f"{recorded_config_hash!r} != {actual_config_hash!r}"
        )
    config_file_sha256 = hashlib.sha256(config_path.read_bytes()).hexdigest()
    if artifact.get("config_file_sha256") != config_file_sha256:
        raise ValueError("windows artifact config file hash differs from the supplied config")

    sources = tuple(Source.model_validate(item) for item in artifact["sources"])
    canonical_sources = json.dumps(
        [source.model_dump(mode="json") for source in sources],
        sort_keys=True,
        separators=(",", ":"),
    )
    source_set_sha256 = hashlib.sha256(canonical_sources.encode("utf-8")).hexdigest()
    if artifact.get("source_set_sha256") != source_set_sha256:
        raise ValueError("windows artifact source set hash does not match its source records")
    windows = tuple(ObservationWindow.model_validate(item) for item in artifact["windows"])
    grouped: dict[str, list[ObservationWindow]] = defaultdict(list)
    for window in windows:
        grouped[window.pass_id].append(window)

    regional_groups = {
        pass_id: tuple(group)
        for pass_id, group in grouped.items()
        if any(window.feasible for window in group)
    }
    pass_reports = [
        _measure_pass(pass_id, regional_groups[pass_id], sources, scenario)
        for pass_id in sorted(regional_groups)
    ]
    lower_bounds = [row["selected_acquisitions_lower_bound"] for row in pass_reports]
    return {
        "evidence_type": "independent_checker_capacity_lower_bound",
        "method": (
            "deterministic chronological first-fit insertion over acquisition options; "
            "each proposed plan is accepted only when the independent checker reports zero "
            "violations; no solver or policy module is imported"
        ),
        "input": {
            "windows_path": str(windows_path.relative_to(repo_root)),
            "windows_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "artifact_status": artifact.get("artifact_status"),
            "model_config_hash": actual_config_hash,
            "config_file_sha256": config_file_sha256,
            "source_set_sha256": source_set_sha256,
            "source_count": len(sources),
            "seeded_source_count": sum(
                source.seeded_from_plume_id is not None for source in sources
            ),
            "uniform_fill_count": sum(source.seeded_from_plume_id is None for source in sources),
        },
        "pass_count": len(pass_reports),
        "window_group_count": len(grouped),
        "minimum_selected_acquisitions_lower_bound_per_pass": min(lower_bounds, default=0),
        "passes_with_at_least_four_validated_acquisitions": sum(
            count >= 4 for count in lower_bounds
        ),
        "passes": pass_reports,
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--windows",
        default="data/fixtures/windows_base_candidate.json",
        help="repository-relative windows artifact path",
    )
    parser.add_argument(
        "--config",
        default="configs/base.yaml",
        help="repository-relative scenario config path",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="optional output file (otherwise JSON is written to stdout)",
    )
    args = parser.parse_args()
    report = build_capacity_report(
        repo_root / args.windows,
        repo_root / args.config,
        repo_root=repo_root,
    )
    output = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.output:
        (repo_root / args.output).write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
