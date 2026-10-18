"""Serve the production console and read-only artifact API from one origin.

Run from the repository root: uvicorn scripts.hosted_app:app --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import os
from pathlib import Path

from aether.api import create_app
from aether.config import load_scenario
from aether.contracts import RunRecord
from aether.ingestion import load_pinned_plume_dataset
from fastapi.staticfiles import StaticFiles

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
if spec is None:
    raise RuntimeError("Hosted demonstration requires the configured pinned dataset")
dataset = load_pinned_plume_dataset(
    root / spec.manifest, expected_manifest_sha256=spec.manifest_sha256, repo_root=root
)
for record in records:
    if (
        record.input_dataset is None
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


@app.get("/healthz", include_in_schema=False)
def health() -> dict[str, str | int]:
    return {"status": "ok", "mode": "offline simulated replay", "runs": len(records)}


# Registered API routes resolve before this final static mount. Browser requests stay same-origin.
app.mount("/", StaticFiles(directory=static_root, html=True), name="console")
