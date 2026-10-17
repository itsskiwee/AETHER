"""Lane L9 read-only FastAPI views over run artifacts (PRD 12).

Run artifacts are the source of truth. Routes validate run files against ``RunRecord`` and never
read hidden simulation truth or calculate scientific results.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from aether.contracts.models import RunRecord


def create_app(run_root: str | Path | None = None) -> FastAPI:
    """Create the read-only artifact API; ``run_root`` defaults to ``AETHER_RUNS_DIR`` or runs/."""
    root = Path(run_root or os.environ.get("AETHER_RUNS_DIR", "runs")).resolve()
    app = FastAPI(title="AETHER Run Archive", version="1.0.0", docs_url="/api/docs")

    def read_run(run_id: str) -> RunRecord:
        # IDs are directory names, but resolve and check containment to reject traversal.
        path = (root / run_id / "run.json").resolve()
        if path.parent.parent != root:
            raise HTTPException(status_code=404, detail="Run artifact not found")
        if not path.is_file():
            example_path = root.parent / "docs" / "examples" / "run.json"
            if example_path.is_file():
                try:
                    example = RunRecord.model_validate_json(example_path.read_text(encoding="utf-8"))
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
        if not root.is_dir():
            return []
        rows = []
        for path in sorted(root.glob("*/run.json")):
            try:
                record = RunRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValidationError, ValueError):
                continue
            rows.append({
                "run_id": record.run_id,
                "policy_id": record.policy_id,
                "scenario_id": record.scenario_id,
                "family": record.family,
                "seed": record.seed,
            })
        example_path = root.parent / "docs" / "examples" / "run.json"
        if example_path.is_file():
            try:
                example = RunRecord.model_validate_json(example_path.read_text(encoding="utf-8"))
                if not any(item["run_id"] == example.run_id for item in rows):
                    rows.append({"run_id": example.run_id, "policy_id": example.policy_id, "scenario_id": example.scenario_id, "family": example.family, "seed": example.seed})
            except (OSError, ValidationError, ValueError):
                pass
        return rows

    @app.get("/api/example")
    def get_example() -> RunRecord:
        path = root.parent / "docs" / "examples" / "run.json"
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
        path = root.parent / "benchmark-results.csv"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Benchmark results are not available")
        with path.open(newline="", encoding="utf-8") as handle:
            return JSONResponse(list(csv.DictReader(handle)))

    return app


app = create_app()
