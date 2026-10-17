# AETHER — rules for every coding agent

AETHER is a **research prototype**: a simulated planner deciding which methane sources virtual satellites should observe next. Scientific integrity matters more than features. Read these before writing code:

1. `Implementation/Work_Plan.md`: your lane, tasks, acceptance criteria, ownership.
2. `Implementation/Parameter_Register.md`: every number and its source.
3. The `__init__.py` docstring of the package you implement: its interface contract.
4. `Implementation/AETHER_Product_Requirements_Document.md`: full requirements (search it; don't load it all).

## Setup and commands

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev,geo]'
pytest                      # all offline tests; must stay green
pytest -m network           # only with credentials; never required in CI
ruff check . && ruff format --check .
python -m aether.cli validate --config ../configs/base.yaml   # benchmark base
python -m aether.cli validate --config ../configs/demo.yaml   # base + scripted demo event
```

Python ≥ 3.12 (3.14 verified for numpy, ortools, sgp4, skyfield, pydantic).

## Hard rules (a PR that breaks one is rejected)

1. **Provenance never changes.** `REAL_OBSERVATION` records come only from `aether.ingestion`. Simulated records are `SIMULATED_OBSERVATION`. Truth is `SIMULATED_GROUND_TRUTH`. Nothing converts one into another.
2. **Truth isolation.** Only `aether.simulation` and `aether.evaluation` may read `bundle.truth`, `TruthHistory`, `cloud_truth` or `wind_truth`. Planner-side packages get `bundle.model` and forecasts. `tests/unit/test_truth_isolation.py` enforces this; never weaken it.
3. **Missing ≠ negative.** `INVALID_ACQUISITION` and `NOT_OBSERVED` never update an emission belief. A missing plume row is never a non-detection. A null flux stays null.
4. **No unseeded randomness.** Use `aether.rng.keyed_rng(seed, namespace, *key)`. No `np.random.*` globals, no `random` module, no wall-clock-dependent logic in the simulation.
5. **UTC only.** Timezone-aware datetimes everywhere; contracts reject naive ones.
6. **Units in names.** `_kg_h`, `_m_s`, `_deg`, `_s`, `_bytes`, `_wh`, `_bits`. Convert kg/s to kg/h exactly once, explicitly.
7. **No invented numbers.** A constant not in `Parameter_Register.md` needs a new PR-ID row in the same PR.
8. **Real libraries for physics.** Skyfield/sgp4 for orbits and frames, CP-SAT for optimization. No hand-rolled Earth rotation.
9. **The checker is independent.** `planning/checker.py` imports nothing from `planning/cpsat.py` or `planning/policies.py`, and does not call `orbit.slew_time_s`. It recomputes geometry itself.
10. **One seed.** Only `ScenarioConfig.random_seed` exists. Derive every stream with `keyed_rng`/`derive_seed`. Never add a per-subsystem seed to config.
11. **Benchmarks use `configs/base.yaml`.** `demo.yaml` has scripted events and is for the demo only.
12. **Read the planner side's inputs carefully.** Belief updates use `wind_estimate_m_s`, never true wind. Policies get `bundle.model` and forecast-only weather.
13. **Honest wording.** Never write "NASA tasking", "detected leak", "verified reduction", "optimal" (unless the solver status is OPTIMAL), or "% better" without a CI. Use the allowed wording in PRD §22.3.
14. **No network in tests** unless the test is marked `@pytest.mark.network`.
15. **Stay in your lane's directories** (Work_Plan.md "Lanes"). Contract changes go through L1.
16. **Network only through the policy.** Only `aether.ingestion`, `aether/weather/era5*`, `aether/orbit/ephemeris*` and `scripts/` may import HTTP/socket libraries. Pass every URL through `aether.netpolicy.require_allowed_url`, call `assert_public_address` before connecting, and use `netpolicy.TIMEOUTS_S`. Never `pickle`/`joblib`, never `yaml.load` (use `yaml.safe_load`). `tests/unit/test_security_baseline.py` enforces this; see `SECURITY.md`.
17. **Two import homes.** Data records (`ObservationWindow`, `Plan`, `SimulatedAcquisition`, ...) come from `aether.contracts`. Config types (`ScenarioConfig`, `SpacecraftProfile`, `SensorProfile`, `AttitudeConfig`, `*Config`) come from `aether.config`. They are never re-exported across, and a guard test enforces this.

## Testing expectations

- Every acceptance criterion in your task has a test that would fail without your change.
- Scientific functions get closed-form or brute-force oracle tests, not just "runs without error".
- Prefer Hypothesis property tests for invariants (monotonicity, probability normalization, no constraint violations).

## Git

- Branch `lane/<TASK-ID>-short-name` from `main`; small PRs; rebase before opening.
- Commit messages: `<TASK-ID>: imperative summary`.
- Never commit credentials, `.netrc`, downloaded raw data outside `data/fixtures/`, or `runs/` output.
