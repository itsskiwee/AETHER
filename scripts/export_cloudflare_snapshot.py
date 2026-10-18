"""Export the read-only replay API as static Cloudflare Worker assets.

Run after building ``frontend/dist`` and installing ``backend[api,dev,geo]``.
Responses are produced by the same FastAPI app used for local hosting; no scientific
results are recomputed and no external network requests are made here.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = Path(os.environ.get("AETHER_STATIC_DIR", ROOT / "frontend" / "dist"))
SNAPSHOT_ROOT = STATIC_ROOT / "_aether_snapshot__"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

os.environ["AETHER_PROJECT_ROOT"] = str(ROOT)
os.environ["AETHER_RUNS_DIR"] = str(ROOT / "data" / "fixtures" / "hosted_replay")
os.environ["AETHER_BENCHMARK_DIR"] = str(
    ROOT / "data" / "fixtures" / "hosted_replay" / "benchmark"
)
os.environ["AETHER_STATIC_DIR"] = str(STATIC_ROOT)

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from scripts.hosted_app import app  # noqa: E402


def write_response(client: TestClient, route: str, relative_path: str) -> int:
    response = client.get(route)
    if response.status_code != 200:
        raise RuntimeError(f"Cannot snapshot {route}: HTTP {response.status_code}")
    output = SNAPSHOT_ROOT / relative_path
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(response.content)
    return len(response.content)


def main() -> int:
    if not (STATIC_ROOT / "index.html").is_file():
        raise RuntimeError("frontend/dist/index.html is missing; build the frontend first")

    exact_routes = {
        "/api/runs": "runs.json",
        "/api/project": "project.json",
        "/api/project/historical-context": "project-historical-context.json",
        "/api/live-context": "live-context.json",
        "/api/benchmark-results.csv": "benchmark-results.json",
        "/api/benchmark-confidence-intervals.json": "benchmark-confidence-intervals.json",
        "/api/benchmark-protocol": "benchmark-protocol.json",
        "/api/research-status": "research-status.json",
        "/api/development-timing.json": "development-timing.json",
        "/api/example": "example.json",
        "/openapi.json": "openapi.json",
        "/healthz": "healthz.json",
    }
    run_routes = {
        "": "run.json",
        "/windows": "windows.json",
        "/plans": "plans.json",
        "/manifest.json": "manifest.json",
        "/historical-context": "historical-context.json",
        "/performance.json": "performance.json",
        "/export": "export.zip",
    }

    total_bytes = 0
    with TestClient(app, raise_server_exceptions=True) as client:
        for route, relative_path in exact_routes.items():
            total_bytes += write_response(client, route, relative_path)

        runs_response = client.get("/api/runs")
        runs_response.raise_for_status()
        runs = runs_response.json()
        if not isinstance(runs, list) or not runs:
            raise RuntimeError("The hosted replay archive contains no runs")

        for row in runs:
            run_id = row.get("run_id") if isinstance(row, dict) else None
            if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
                raise RuntimeError("The hosted replay archive has an invalid run identifier")
            for suffix, filename in run_routes.items():
                route = f"/api/runs/{quote(run_id, safe='')}{suffix}"
                relative_path = f"runs/{run_id}/{filename}"
                total_bytes += write_response(client, route, relative_path)

    print(
        f"Exported {len(exact_routes) + len(runs) * len(run_routes)} API snapshots "
        f"({total_bytes:,} bytes) to {SNAPSHOT_ROOT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
