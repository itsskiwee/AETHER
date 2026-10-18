# AETHER
A research prototype: we developed and tested a **simulated** methane observation planner. It decides which methane source hypotheses virtual, taskable Earth-observation satellites should look at next, so as to collect the most useful evidence.

**SIMULATED MISSION · offline replay.** NASA EMIT provided real observed methane plume records. The checked-in pinned sample is 20 EMIT L2B CH4PLM V002 Permian plume records from 2023–2024, together with their provider metadata and raster files. These records place the simulated source hypotheses. They are historical location context only. They never set simulated truth, present-day activity or the flux prior. Spacecraft, sensor responses, weather, acquisitions and ground truth are all simulated. AETHER does not task real satellites, and it does not verify emissions or reductions.

## Quickstart (fresh checkout, offline)

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

The first 72-hour run computes orbit geometry, which took about 6.5 minutes on the reference machine. Set `AETHER_WINDOW_CACHE_DIR` to reuse it across runs, policies and seeds; outputs are byte-identical with or without the cache.

## Status (18 Oct 2026)

The implementation is integrated. Scientific acceptance is **not** complete. See [`docs/p0-requirements-evidence.md`](docs/p0-requirements-evidence.md) for every criterion with its evidence and status, and [`docs/validation-report.md`](docs/validation-report.md) for gate results, including the failures:

- **G1-F capacity fails on the pinned scenario.** It has 7 passes per 72 h, but one pass supports only 2 acquisitions; the minimum is 4.
- **G4.5 discriminability failed** in the synthetic-only m0 pilot. The pinned-data all-family results are in the validation report.
- The protocol is **unlocked**. No holdout benchmark has run, and no policy-comparison claim is made.

## Documents

- Requirements: `Implementation/AETHER_Product_Requirements_Document.md` (amended by `Implementation/PRD_Amendments.md`)
- Parameters: `Implementation/Parameter_Register.md`
- Plan, ownership and the integration handoff: `Implementation/Work_Plan.md`, `AGENTS.md`
- Data: `docs/dataset-interface.md`, `docs/ingestion-adapters.md`, `DATA_LICENSES.md`, `CITATIONS.md`
- Console walkthrough: `docs/demo-console.md`
