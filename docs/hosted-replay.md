# Host the recorded demonstration

The production console and read-only FastAPI API can run in one container. It serves
the checked-in accepted replay under `data/fixtures/hosted_replay`, without running
the simulation or requiring credentials. This makes a public repository usable for
local replay and a container host. A Cloudflare deployment configuration is included;
account setup and publication are described in [Cloudflare hosting](cloudflare-hosting.md).

## Container host

```bash
docker build -t aether-replay .
docker run --rm -p 8080:8080 aether-replay
```

Open http://localhost:8080. For a container hosting service, use the repository
Dockerfile, set its HTTP port to 8080 (or provide PORT), and set the health check
to `/healthz`. The API is at `/api/docs`. Both console and API use the same origin;
there is no development proxy or separate API URL to configure. Use the hosting
service's HTTPS endpoint for public access. No account keys belong in this repo.

## Cloudflare

The Cloudflare Worker with Static Assets, GitHub Workers Builds configuration, account
requirements and cost notes are in [Cloudflare hosting](cloudflare-hosting.md). Open the
[hosted globe](https://aether-replay-hosted.ryan-rawal43.workers.dev/?view=globe).

## Run without Docker

### Optional current public satellite context

Open `/?view=live` or follow Satellite context in the replay header. The view uses
public CelesTrak GP elements for Landsat 8/9 and NASA CMR EMIT V002 catalogue
metadata. Positions are SGP4/Skyfield estimates, not telemetry. NASA catalogue
entries are not real-time methane measurements: the newest observation returned
during initial connection was September 2025.

```bash
# Container: explicitly enable the provider refresh worker
docker run --rm -p 8080:8080 -e AETHER_ENABLE_LIVE=1 aether-replay

# Native, after dependency installation and production frontend build
AETHER_ENABLE_LIVE=1 AETHER_PYTHON=backend/.venv/bin/python sh scripts/serve_hosted.sh
```

The updater runs separately from the read-only API. Browser refresh recalculates
positions using cached elements; it never downloads from providers per visitor.
GP inputs are refreshed at most every two hours under CelesTrak's usage policy.
An upstream non-200 response stops the worker for investigation. Retained data
keep their original ages, hashes and timestamps; stale inputs are labelled.
Without the updater, the view is a timestamped cache. Snapshots are ignored by Git
and excluded from Docker build context. No Earthdata credentials are needed for
these catalogue queries; protected raster downloads can require authentication.
Current feeds do not alter the saved scientific experiment or establish access
to a spacecraft's sensors or commanding interfaces.

### Native replay commands

```bash
python -m venv backend/.venv
backend/.venv/bin/pip install -e './backend[geo,api]'
npm --prefix frontend ci
npm --prefix frontend run build
PYTHONPATH=backend backend/.venv/bin/python -m uvicorn scripts.hosted_app:app --host 127.0.0.1 --port 8080
```

## Refresh the sample after a new accepted demo

Generate and verify the demo through `scripts/demo.sh` first. Keep that original
archive. The following command writes a new destination and refuses to overwrite
existing evidence:

```bash
python scripts/prepare_hosted_replay.py --demo runs/demo-pinned --destination data/fixtures/hosted_replay_v2
```

Review and commit the new fixture deliberately, then set AETHER_RUNS_DIR to that
folder. The host validates run contracts, dataset hashes and schedule acceptance
at startup. It does not recompute benchmarks, inference or hidden truth.

## Evidence and limits

The sample contains 20 historical EMIT-seeded locations, zero uniform fills and
two simulated policies. Adaptive has 47 checked plans and 51 acquisitions;
largest-first has 41 checked plans and 37 acquisitions. Both use 1,494 windows,
with zero recorded checker violations. Missing rates and unknown retrieval time
remain explicit. The forecast refresh changes no selected option in these runs.
The sample proves no adaptive advantage, passed capacity gate or holdout result.

The sample now includes the completed six-run development comparison, two seeds,
its bootstrap intervals and measured timing. It remains preliminary, unlocked and
insufficient for a research verdict. AETHER_BENCHMARK_DIR can point at a separately
reviewed completed evaluator directory. Missing artifacts remain unavailable.
