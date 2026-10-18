"""Serve the production console and read-only artifact API from one origin.

Run from the repository root: uvicorn scripts.hosted_app:app --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml
from aether.api import create_app
from aether.config import load_scenario
from aether.contracts import RunPerformance, RunRecord
from aether.ingestion import load_pinned_plume_dataset
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from scripts.live_context import DEFAULT_SNAPSHOT, context

root = Path(__file__).resolve().parents[1]
run_root = Path(os.environ.get("AETHER_RUNS_DIR", root / "data/fixtures/hosted_replay"))
static_root = Path(os.environ.get("AETHER_STATIC_DIR", root / "frontend/dist"))
if not (static_root / "index.html").is_file():
    raise RuntimeError(
        "Production console missing: run npm --prefix frontend run build"
    )
paths = sorted(run_root.glob("*/run.json"))
if not paths:
    raise RuntimeError(
        "No replay records: run scripts/prepare_hosted_replay.py --demo <archive>"
    )
records = [RunRecord.model_validate_json(path.read_bytes()) for path in paths]
cfg = load_scenario(root / "configs/base.yaml").model
spec = cfg.sources.plume_dataset
dataset = (
    None
    if spec is None
    else load_pinned_plume_dataset(
        root / spec.manifest,
        expected_manifest_sha256=spec.manifest_sha256,
        repo_root=root,
    )
)
for record in records:
    if record.input_dataset is not None and (
        dataset is None
        or record.input_dataset.manifest_sha256 != dataset.manifest_sha256
    ):
        raise RuntimeError(
            f"Replay dataset does not match project dataset: {record.run_id}"
        )
    if len(record.plans) != len(record.validations) or any(
        not item.ok or item.violations for item in record.validations
    ):
        raise RuntimeError(f"Replay schedule validation failed: {record.run_id}")

app = create_app(run_root=run_root, project_root=root)


@app.get("/api/research-status")
def research_status() -> dict:
    artifacts = {
        "capacity": "experiments/results/g1f-pinned-base/g1f.json",
        "synthetic_discriminability_pilot": "experiments/results/g45-pilot-synthetic-m0/gate.json",
    }
    result = {
        name: json.loads((root / path).read_bytes())
        if (root / path).is_file()
        else None
        for name, path in artifacts.items()
    }
    protocol = yaml.safe_load((root / "experiments/protocol.yaml").read_text())
    return {
        **result,
        "protocol_locked": bool(protocol.get("locked", False)),
        "note": "Recorded gate artifacts; scopes and input identities remain in each artifact.",
    }


@app.get("/api/runs/{run_id}/performance.json")
def run_performance(run_id: str) -> dict:
    if run_id not in {record.run_id for record in records}:
        raise HTTPException(status_code=404, detail="Unknown replay run")
    path = run_root / run_id / "performance.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Measured timing unavailable")
    performance = RunPerformance.model_validate_json(path.read_bytes())
    if performance.run_id != run_id:
        raise HTTPException(
            status_code=503, detail="Timing does not match selected run"
        )
    return performance.model_dump(mode="json")


@app.get("/api/runs/{run_id}/export")
def run_export(run_id: str) -> FileResponse:
    if run_id not in {record.run_id for record in records}:
        raise HTTPException(status_code=404, detail="Unknown replay run")
    path = run_root / "exports" / f"{run_id}.zip"
    if not path.is_file():
        path = run_root / f"{run_id}.zip"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Export unavailable")
    return FileResponse(path, media_type="application/zip", filename=f"{run_id}.zip")


@app.get("/api/live-context")
def live_context() -> dict:
    try:
        return context(Path(os.environ.get("AETHER_LIVE_CONTEXT", DEFAULT_SNAPSHOT)))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=503, detail="Provider context is malformed or unavailable"
        ) from exc


@app.get("/healthz", include_in_schema=False)
def health() -> dict[str, str | int]:
    return {"status": "ok", "mode": "offline simulated replay", "runs": len(records)}


# Registered API routes resolve before this final static mount. Browser requests stay same-origin.
app.mount("/", StaticFiles(directory=static_root, html=True), name="console")
