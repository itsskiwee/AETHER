# Host the recorded demonstration

The production console and read-only FastAPI API can run in one container. It serves
the checked-in accepted replay under `data/fixtures/hosted_replay`, without running
the simulation or requiring credentials. This makes a public repository usable for
local replay and a container host. Publication, repository visibility and paid hosting
are separate actions; this branch does not perform them.

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

## Run without Docker

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

The comparison panel will honestly report unavailable until authoritative completed
comparison artifacts are supplied via AETHER_BENCHMARK_DIR. Existing exploratory
experiments are not silently substituted for a registered benchmark.
