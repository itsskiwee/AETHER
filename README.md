# AETHER

**Open-source methane observation planning.** AETHER asks where a methane-hunting satellite should look next. It combines **real** NASA EMIT plume observations and **real** satellite orbits with a **simulated** fleet and planner that decides which site to observe to learn the most. Every run is reproducible and every input is fingerprinted. MIT licensed.

## Run it on your machine

You need **Python 3.12+**, **Node.js 20+** and **Git**. Then:

```bash
git clone https://github.com/itsskiwee/AETHER.git
cd AETHER
bash scripts/quickstart.sh                                        # macOS / Linux
powershell -ExecutionPolicy Bypass -File scripts\quickstart.ps1   # Windows
```

The script installs everything into the project folder, fetches fresh public data, builds the app and opens **http://127.0.0.1:8080/?view=globe**. The first run takes a few minutes. Add `--offline` (macOS/Linux) or `-Offline` (Windows) to skip the data refresh and use the snapshot in the repository.

**What you get**

- **A 3D globe** showing the ISS (which carries NASA EMIT), Landsat 8 and 9 and Sentinel-5P, with positions calculated in your browser from published orbital elements. It also shows the 20 real EMIT plume sites in the Permian Basin and a replay of the simulated mission.
- **Real data pages**: the 20 pinned EMIT V002 records, the newest EMIT plume files over the Permian from NASA's CMR catalogue, and the next real satellite passes over the sites.
- **Simulation pages**: the planner's decision timeline, how its beliefs change, the policy test with its honest results, and verifiable run exports.

**Where the data comes from.** Each run of the quickstart refreshes orbital elements from CelesTrak and the EMIT plume list from NASA CMR. Both are public and need no account. The 20 EMIT records, the planetary ephemeris and the Earth-orientation tables are pinned in the repository and verified by SHA-256 on every run. If a refresh fails, the last good copy is kept; nothing is made up.

## What is real and what is simulated

| Real | Simulated |
|---|---|
| 20 NASA EMIT plume records (2023–2024), with locations, rates and uncertainties | Four virtual satellites: **Pip** (`vsat_a`), **Wren** (`vsat_b`), **Juniper** (`vsat_c`) and **Mochi** (`vsat_d`) |
| Newest EMIT plume listings from NASA CMR | Their sensor, the weather and every observation outcome |
| Orbits of the ISS, Landsat 8/9 and Sentinel-5P (calculated positions, not telemetry) | The hidden "true" emissions used to score planners |
| Upcoming real passes over the plume sites | The planner's decisions (OR-Tools CP-SAT), each re-checked by an independent checker |

AETHER does not task real satellites and does not verify emissions or reductions. The fleet names are display names only (`frontend/src/fleet.ts`); configs, run records and export hashes keep the IDs.

**Line endings.** The repository's `.gitattributes` disables line-ending conversion, because every pinned data file is checked by SHA-256 and byte size. If you cloned with an older Git that ignored it, re-clone with `git clone -c core.autocrlf=false`.

<details><summary>Manual setup (instead of the quickstart)</summary>

```bash
python -m venv backend/.venv
backend/.venv/bin/pip install -e './backend[geo,api]'
npm --prefix frontend ci
PYTHONPATH=backend:. backend/.venv/bin/python -m scripts.build_globe_data   # add --offline to skip the refresh
npm --prefix frontend run build
PYTHONPATH=backend backend/.venv/bin/python -m uvicorn scripts.hosted_app:app --host 127.0.0.1 --port 8080
```

On Windows, use `backend\.venv\Scripts\python` and separate `PYTHONPATH` entries with `;`. For container hosting, see [hosted replay](docs/hosted-replay.md); for Cloudflare, see [Cloudflare hosting](docs/cloudflare-hosting.md). The workspace is described in [the workspace guide](docs/frontend-workspace.md).
</details>

## Contributing

Issues and pull requests are welcome. Read [`AGENTS.md`](AGENTS.md) first: it holds the project's hard rules (provenance never changes, missing data is never a negative, no unseeded randomness, honest wording). The offline test suite must stay green (`cd backend && pytest`), and so must the browser tests (`npm --prefix frontend run test:e2e`). Security reports: see [`SECURITY.md`](SECURITY.md).

## Regenerate the demo and development comparison

```bash
python -m venv backend/.venv
backend/.venv/bin/pip install -e './backend[dev,geo,api]'
npm --prefix frontend ci
bash scripts/demo.sh runs/demo          # actual runs, replay check, verified exports
bash scripts/serve-demo.sh runs/demo    # API + console on http://127.0.0.1:4173
```

`configs/base.yaml` pins `data/manifests/emit_permian.json` by SHA-256. The runner verifies the manifest, the normalized records and all 40 raw files before it builds any source. If a file is missing or altered, the run stops; it never falls back silently. Add `--synthetic-only` to `windows`, `simulate`, `benchmark` or the G4.5 gate for the explicit uniform-fill mode. The mode is recorded in config hashes and outputs.

```bash
cd backend
python -m pytest -q                       # offline suite
python -m aether.cli validate --config ../configs/base.yaml
python -m aether.cli simulate --config ../configs/base.yaml --policies largest_first,adaptive_eig --seed 1000 --output-dir ../runs/dev
python -m aether.cli export --run-dir ../runs/dev --run-id <run_id> --output ../runs/<run_id>.zip
python -m aether.cli verify-export --archive ../runs/<run_id>.zip
```

For byte-identical replay, run with a fixed BLAS thread count (`OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1`; `scripts/demo.sh` sets it). Without it, decisions are unchanged but the last floating-point digit can differ.

The first 72-hour run computes orbit geometry, which took about 6.5 minutes on the reference machine. Set `AETHER_WINDOW_CACHE_DIR` to reuse it across runs, policies and seeds; outputs are byte-identical with or without the cache.

## Status (18 Oct 2026)

The implementation is integrated. Scientific acceptance is **not** complete. See [`docs/p0-requirements-evidence.md`](docs/p0-requirements-evidence.md) for every criterion with its evidence and status, and [`docs/validation-report.md`](docs/validation-report.md) for gate results, including the failures:

- **G1-F capacity fails on the pinned scenario.** It has 7 passes per 72 h, but one pass supports only 2 acquisitions; the minimum is 4.
- **G4.5 discriminability fails**, both in the synthetic-only m0 pilot and on the pinned scenario in all six protocol families (30 tuning seeds each). Even an oracle-informed reference does not separate from random, so the registered benchmark would not be informative as configured. A scenario decision is pending.
- SCI-10 calibration is mixed: the random reference passes; adaptive_eig fails one reliability rule on two tiny bins (see the validation report).
- The protocol is **unlocked**. No holdout benchmark has run, and no policy-comparison claim is made.

## Documents

- Requirements: `Implementation/AETHER_Product_Requirements_Document.md` (amended by `Implementation/PRD_Amendments.md`)
- Parameters: `Implementation/Parameter_Register.md`
- Plan, ownership and the integration handoff: `Implementation/Work_Plan.md`, `AGENTS.md`
- Data: `docs/dataset-interface.md`, `docs/ingestion-adapters.md`, `DATA_LICENSES.md`, `CITATIONS.md`
- Console walkthrough: `docs/demo-console.md`
