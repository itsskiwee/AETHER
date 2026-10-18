# Orbit model report — base scenario candidate

**Status:** Candidate output for Agent 5 independent review. It is not a golden fixture or an
independent geometry validation.

## Reproduction inputs

Generated with `python ../scripts/build_orbit_candidate.py` from `backend/`, using `configs/base.yaml`
and its configured 72-hour horizon. The source constructor received no plume records: no
authenticated, source-verified EMIT granule is available in this workspace. The 20 sources are
therefore synthetic uniform fills in the configured region, seeded with the scenario run seed.

| Input | Value |
|---|---|
| Scenario | `permian-p0` |
| Model config hash | `2637825a8e2f0b085d5291607a6ee969c5e3d51ba14fddaee2ec3b7deecf62d6` |
| Base YAML SHA-256 | `671384c6969baf526c9bf0e2216145c66d2b69d3fc322489bf00715900d49128` |
| Source count / seed | 20 / 42017 |
| Source set SHA-256 | `e0999f0922daad427dc11a0df427c818cdf481eaa266296d4a1402c92c079afa` |
| DE421 SHA-256 | `a20a7139da04cbc462454634918e9a9ca69127044e2cc9d4f9c16e238d2deedc` |
| IERS `finals2000A.all` SHA-256 | `bfa2066aab0400b075357f573af6081e0068a518993609eee0c5ca991bab0845` |
| Skyfield / sgp4 | 1.55 / 2.27 |

The window candidate records the config hashes, source set, time range, software versions, and both
verified input hashes alongside serialized windows:
`data/fixtures/windows_base_candidate.json`. Its status field is
`CANDIDATE_PENDING_AGENT5_REVIEW`; promote it to `backend/tests/golden/windows_base.json` only
after that independent review.

## Observed output

| Quantity | Candidate result |
|---|---:|
| Spacecraft regional passes over 72 h | 6 |
| Windows emitted, feasible and rejected | 1,469 |
| Feasible source windows | 88 |
| Feasible source opportunities per pass, min / median / max | 5 / 20 / 20 |
| Acquisition throughput proxy per pass, median / max | 11 / 11 |

The throughput proxy takes one lowest-off-nadir option per feasible source window, orders those
representative options by start time, and divides each pass's observed span by exposure plus the
median consecutive LOS slew-and-settle time. It describes geometric throughput in this orbit
output; it is not a schedule feasibility result and does not apply source, storage, energy, or
per-orbit limits. Agent 5's independent check remains necessary before interpreting the proxy as a
capacity gate.

## Implementation and validation

The orbit module constructs virtual satellites with SGP4 and uses Skyfield for TEME-to-ITRS,
target geometry and the Sun. The Skyfield timescale is parsed from the pinned IERS table. Both the
IERS file and local DE421 ephemeris are SHA-256 and byte-size checked before use; the runtime path
does not fall back to downloads. Window sampling uses the configured 2-second coarse interval,
refines boundaries to the configured tolerance, and evaluates LOS independently at each
acquisition option's start time.

Unit tests cover propagated altitude and period, SGP4 error propagation, every configured LTDN,
overhead and 2,000 km off-track geometry, night rejection, the short edge-of-field window,
boundary refinement, option-time LOS, and slew/settle calculations. Source construction tests
cover seeded repeatability, region bounds, geodesic separation, plume clustering plus fill, and
unattributed provenance. The targeted run
`pytest -q tests/unit/test_orbit_engine.py tests/unit/test_source_construction.py tests/unit/test_ingestion.py`
completed with **14 passed**. Ruff check and format check passed on all owned Python files and the
candidate builder. A shared full-suite run was also started, but its final traceback/result was not
captured; it showed at least one failure among concurrently changing lanes, so no full-suite pass
is claimed here.

## External data status

Offline ingestion is covered by the explicitly synthetic fixture and temporary malformed-input
tests. The real EMIT V002 mapping is **not validated against a downloaded granule**. That requires
an authenticated NASA Earthdata session and a source-verified V002 granule; no raw provider data
are present. Carbon Mapper is optional P1 and no provider records are stored. A plume row is never
turned into an acquisition, and a missing plume row is never treated as a non-detection.
