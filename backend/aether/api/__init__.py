"""Lane L9 read-only FastAPI views over run artifacts (PRD 12).

Run artifacts are the source of truth. Routes validate run files against ``RunRecord`` and never
read hidden simulation truth or calculate scientific results.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from aether.contracts.models import RunRecord

# backend/aether/api/__init__.py -> the repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def create_app(
    run_root: str | Path | None = None,
    benchmark_root: str | Path | None = None,
    project_root: str | Path | None = None,
) -> FastAPI:
    """Create the read-only artifact API.

    ``project_root`` (configs, experiments, docs/examples) defaults to ``AETHER_PROJECT_ROOT`` or
    the repository root. ``run_root`` defaults to ``AETHER_RUNS_DIR`` or ``<project>/runs``.
    ``benchmark_root`` (the evaluator's ``out_dir``) defaults to ``AETHER_BENCHMARK_DIR`` or
    ``<runs>/benchmark``.
    """
    project_root = Path(project_root or os.environ.get("AETHER_PROJECT_ROOT", PROJECT_ROOT))
    project_root = project_root.resolve()
    root = Path(run_root or os.environ.get("AETHER_RUNS_DIR", project_root / "runs")).resolve()
    bench = Path(benchmark_root or os.environ.get("AETHER_BENCHMARK_DIR", root / "benchmark"))
    bench = bench.resolve()
    example_path = project_root / "docs" / "examples" / "run.json"
    app = FastAPI(title="AETHER Run Archive", version="1.0.0", docs_url="/api/docs")

    def read_yaml(path: Path) -> dict[str, Any]:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise HTTPException(
                status_code=422, detail=f"Project configuration is invalid: {path.name}"
            ) from exc
        if not isinstance(value, dict):
            raise HTTPException(
                status_code=422, detail=f"Project configuration is invalid: {path.name}"
            )
        return value

    def read_run(run_id: str) -> RunRecord:
        # IDs are directory names, but resolve and check containment to reject traversal.
        path = (root / run_id / "run.json").resolve()
        if path.parent.parent != root:
            raise HTTPException(status_code=404, detail="Run artifact not found")
        if not path.is_file():
            if example_path.is_file():
                try:
                    example = RunRecord.model_validate_json(
                        example_path.read_text(encoding="utf-8")
                    )
                    if example.run_id == run_id:
                        return example
                except (OSError, ValidationError, ValueError):
                    pass
            raise HTTPException(status_code=404, detail="Run artifact not found")
        try:
            return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Run artifact is invalid") from exc

    @app.get("/api/runs")
    def list_runs() -> list[dict[str, Any]]:
        rows = []
        for path in sorted(root.glob("*/run.json")) if root.is_dir() else ():
            try:
                record = RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValidationError, ValueError):
                continue
            rows.append(
                {
                    "run_id": record.run_id,
                    "policy_id": record.policy_id,
                    "scenario_id": record.scenario_id,
                    "family": record.family,
                    "seed": record.seed,
                }
            )
        if not rows and example_path.is_file():
            try:
                example = RunRecord.model_validate_json(example_path.read_text(encoding="utf-8"))
                if not any(item["run_id"] == example.run_id for item in rows):
                    rows.append(
                        {
                            "run_id": example.run_id,
                            "policy_id": example.policy_id,
                            "scenario_id": example.scenario_id,
                            "family": example.family,
                            "seed": example.seed,
                        }
                    )
            except (OSError, ValidationError, ValueError):
                pass
        return rows

    @app.get("/api/project")
    def get_project() -> dict[str, Any]:
        """Read the model-side project configuration and explicitly labelled fixture inventory."""
        try:
            return project_snapshot()
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise HTTPException(
                status_code=422, detail="Project configuration is incomplete"
            ) from exc

    def project_snapshot() -> dict[str, Any]:
        config_dir = project_root / "configs"
        base_path = config_dir / "base.yaml"
        if not base_path.is_file():
            base_path = config_dir / "demo.yaml"
        base = read_yaml(base_path)
        region = read_yaml(config_dir / str(base["region_file"]))

        spacecraft = []
        for relative_path in base.get("spacecraft_files", []):
            profile = read_yaml(config_dir / relative_path)
            orbit, attitude, resources = profile["orbit"], profile["attitude"], profile["resources"]
            spacecraft.append(
                {
                    "id": profile["id"],
                    "virtual": profile["virtual"],
                    "profile_version": profile["profile_version"],
                    "sensor_ids": profile["sensor_ids"],
                    "orbit": {
                        key: orbit[key]
                        for key in (
                            "epoch_utc",
                            "plane",
                            "altitude_km",
                            "inclination_deg",
                            "ltdn",
                            "raan_deg",
                            "mean_anomaly_deg",
                        )
                    },
                    "attitude": {
                        key: attitude[key]
                        for key in ("max_off_nadir_deg", "slew_rate_deg_s", "settle_seconds")
                    },
                    "resources": {
                        key: resources[key]
                        for key in (
                            "battery_capacity_wh",
                            "storage_bytes",
                            "max_acquisitions_per_orbit",
                        )
                    },
                }
            )

        sensor_rows = []
        for relative_path in base.get("sensor_files", []):
            sensor = read_yaml(config_dir / relative_path)
            sensor_rows.append(
                {
                    "id": sensor["id"],
                    "calibration_status": sensor["calibration_status"],
                    "gsd_nadir_m": sensor["gsd_nadir_m"],
                    "exposure_seconds": sensor["exposure_seconds"],
                    "min_sun_elevation_deg": sensor["min_sun_elevation_deg"],
                    "q50_ref_kg_h": sensor["pod"]["q50_ref_kg_h"],
                    "q90_ref_kg_h": sensor["pod"]["q90_ref_kg_h"],
                    "ref_wind_m_s": sensor["pod"]["ref_wind_m_s"],
                    "false_positive_prob": sensor["false_positive_prob"],
                    "retrieval_success_prob": sensor["validity"]["retrieval_success_prob"],
                    "data_bytes_per_scene": sensor["costs"]["data_bytes_per_scene"],
                    "energy_wh_per_scene": sensor["costs"]["energy_wh_per_scene"],
                }
            )

        fixture_manifest_path = (
            project_root / "data" / "manifests" / "synthetic_ingestion_examples.json"
        )
        fixture_manifest = (
            json.loads(fixture_manifest_path.read_text(encoding="utf-8"))
            if fixture_manifest_path.is_file()
            else None
        )
        fixture_features = []
        if fixture_manifest:
            for item in fixture_manifest.get("files", []):
                fixture_path = project_root / item["path"]
                if fixture_path.is_file():
                    collection = json.loads(fixture_path.read_text(encoding="utf-8"))
                    for feature in collection.get("features", []):
                        properties = feature.get("properties") or {}
                        geometry = feature.get("geometry") or {}
                        fixture_features.append(
                            {
                                "id": properties.get("Plume_ID", feature.get("id", "unidentified")),
                                "time_utc": properties.get("datetime"),
                                "longitude": properties.get("Longitude_of_max_concentration"),
                                "latitude": properties.get("Latitude_of_max_concentration"),
                                "rate": properties.get("emission_rate_kg_h"),
                                "geometry_type": geometry.get("type", "missing"),
                                "quality": properties.get("quality", "not provided"),
                            }
                        )

        def manifest(name: str) -> dict[str, Any] | None:
            path = project_root / "data" / name / "manifest.json"
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

        protocol_path = project_root / "experiments" / "protocol.yaml"
        protocol = read_yaml(protocol_path) if protocol_path.is_file() else {}

        return {
            "scenario": {
                "id": base.get("scenario_id"),
                "epoch_utc": base.get("simulation_epoch_utc"),
                "horizon_hours": base.get("horizon_hours"),
                "sources_count": base.get("sources", {}).get("count"),
                "policies": base.get("evaluation", {}).get("policies", []),
                "region": {
                    "id": region.get("region_id"),
                    "name": region.get("name"),
                    "bbox_wgs84": region.get("bbox_wgs84"),
                },
                "weather": {
                    "type": base.get("weather", {}).get("type"),
                    "mean_cloud_fraction": base.get("weather", {})
                    .get("cloud", {})
                    .get("mean_cloud_fraction"),
                    "wind_median_m_s": base.get("weather", {}).get("wind", {}).get("median_m_s"),
                },
            },
            "source_model": {
                "placement": base.get("sources", {}).get("placement"),
                "min_separation_m": base.get("sources", {}).get("min_separation_m"),
                "flux_prior": base.get("sources", {}).get("flux_prior"),
                "regimes": base.get("sources", {}).get("regimes", []),
            },
            "planner": {
                "lookahead_hours": base.get("planner", {}).get("lookahead_hours"),
                "replan_on": base.get("planner", {}).get("replan_on", []),
                "weights": base.get("planner", {}).get("weights", {}),
                "utility": base.get("planner", {}).get("utility"),
                "solver": base.get("planner", {}).get("solver", {}),
                "max_visits_per_source_per_solve": base.get("planner", {}).get(
                    "max_visits_per_source_per_solve"
                ),
            },
            "scenario_families": sorted(
                path.stem for path in (config_dir / "scenarios").glob("*.yaml")
            ),
            "spacecraft": spacecraft,
            "sensors": sensor_rows,
            "fixture": {"manifest": fixture_manifest, "features": fixture_features},
            "pinned_data": {
                "earth_orientation": manifest("eop"),
                "planetary_ephemeris": manifest("ephemeris"),
            },
            "benchmark_protocol": {
                "path": "experiments/protocol.yaml",
                "version": protocol.get("protocol_version"),
                "locked": bool(protocol.get("locked", False)),
                "families": protocol.get("families", []),
                "policies": protocol.get("policies", []),
                "primary_metric": protocol.get("primary_metric"),
                "seed_count_rule": protocol.get("seed_count_rule"),
                "seed_files": ["experiments/seeds_dev.txt", "experiments/seeds_holdout.txt"],
            },
        }

    @app.get("/api/example")
    def get_example() -> RunRecord:
        path = example_path
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Example run artifact is not available")
        try:
            return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Example run artifact is invalid") from exc

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> RunRecord:
        return read_run(run_id)

    @app.get("/api/runs/{run_id}/windows")
    def get_windows(run_id: str) -> tuple:
        return read_run(run_id).windows

    @app.get("/api/runs/{run_id}/plans")
    def get_plans(run_id: str) -> tuple:
        return read_run(run_id).plans

    @app.get("/api/benchmark-results.csv")
    def benchmark_results() -> JSONResponse:
        path = bench / "benchmark-results.csv"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Benchmark results are not available")
        with path.open(newline="", encoding="utf-8") as handle:
            return JSONResponse(list(csv.DictReader(handle)))

    @app.get("/api/benchmark-confidence-intervals.json")
    def benchmark_confidence_intervals() -> dict[str, Any]:
        path = bench / "benchmark-confidence-intervals.json"
        if not path.is_file():
            raise HTTPException(
                status_code=404, detail="Benchmark confidence intervals are not available"
            )
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail="Benchmark confidence interval report is invalid"
            ) from exc
        if not isinstance(report, dict) or not isinstance(report.get("comparisons"), list):
            raise HTTPException(
                status_code=422, detail="Benchmark confidence interval report has an invalid shape"
            )
        return report

    @app.get("/api/benchmark-protocol")
    def benchmark_protocol() -> dict[str, Any]:
        path = project_root / "experiments" / "protocol.yaml"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Benchmark protocol is not available")
        try:
            protocol = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise HTTPException(status_code=422, detail="Benchmark protocol is invalid") from exc
        if not isinstance(protocol, dict):
            raise HTTPException(status_code=422, detail="Benchmark protocol has an invalid shape")
        return {
            "protocol_version": protocol.get("protocol_version"),
            "locked": bool(protocol.get("locked", False)),
            "primary_metric": protocol.get("primary_metric"),
            "primary_comparison": protocol.get("primary_comparison"),
            "mandatory_secondary_comparison": protocol.get("mandatory_secondary_comparison"),
            "success_criterion": protocol.get("success_criterion"),
        }

    return app


app = create_app()
