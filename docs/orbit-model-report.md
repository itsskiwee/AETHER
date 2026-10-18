# Orbit model and capacity report

**Status:** The synthetic base candidate passes local and independent feasibility review. The
historical-location sample has seven feasible passes, but one pass supports only two acquisitions,
so it fails the registered G1-F capacity threshold. The historical sample also awaits normalized
data lineage from Codex-1. Capacity evidence is calculated per pass and does not represent a
jointly feasible 72-hour plan. Both artifacts are `CANDIDATE_NOT_GOLDEN`; Codex-3 owns promotion to
`backend/tests/golden/windows_base.json`. Codex-3 rechecked the final artifact hashes and confirmed
the stored schedules and code/input hashes.

## Inputs and provenance

The benchmark candidate uses `configs/base.yaml`, its 72-hour horizon, and the configured random
seed. The default builder creates 20 seeded, uniform-fill source locations because it receives no
plume records. This is the reproducible synthetic baseline, not a real plume population.

| Input | Value |
|---|---|
| Scenario | `permian-p0` |
| Model config SHA-256 | `2637825a8e2f0b085d5291607a6ee969c5e3d51ba14fddaee2ec3b7deecf62d6` |
| `configs/base.yaml` SHA-256 | `671384c6969baf526c9bf0e2216145c66d2b69d3fc322489bf00715900d49128` |
| Source count / seed | 20 / 42017 |
| Source set SHA-256 | `e0999f0922daad427dc11a0df427c818cdf481eaa266296d4a1402c92c079afa` |
| Pinned DE421 SHA-256 | `a20a7139da04cbc462454634918e9a9ca69127044e2cc9d4f9c16e238d2deedc` |
| Pinned IERS `finals2000A.all` SHA-256 | `bfa2066aab0400b075357f573af6081e0068a518993609eee0c5ca991bab0845` |
| Software | `aether` 0.1.0, Skyfield 1.55, sgp4 2.27 |

The candidate artifact records the config, ephemeris/EOP, source-set and code hashes:
`data/fixtures/windows_base_candidate.json` (SHA-256
`fbd83e1977b2f73671c7ba0ffc2e93db689a894e6d62ad0d109d3f126e5d6e35`). Its current code hashes are:

| Code input | SHA-256 |
|---|---|
| Orbit module | `ce109c4e6cda810133805b99049e2319e2574318c9f5e5992e5b703f77602e05` |
| Capacity builder | `8af0d04665dda0c8e48cd48437984e6a95ba583a1a41eabc1aa650c0dfa94d43` |
| CP-SAT solver | `2b286f23ecc9eed6b6a433c563feebf61449d26aa457a27878d07220761b3bec` |
| Schedule checker | `4d62a21b97ab2c678af9822b91a023034ceb78f1f78e0b0b6878db52e1b773ae` |

Capacity metadata was recomputed from the serialized windows; `window_provenance` records the
SHA-256 of the previous candidate from which those windows were reused. The propagation module
was unchanged between window generation and this refresh.

## Orbit acceptance evidence

The production orbit module uses SGP4 for propagation and Skyfield for TEME-to-ITRS conversion,
target geometry, solar position and the pinned timescale. It verifies the local DE421 and IERS
files against their manifests and has no runtime download fallback. The registered orbital values
remain unchanged.

The orbit tests cover the ORB-01..04 criteria: altitude and period tolerances and SGP4 errors;
configured LTDN checks; overhead, off-track, night, short edge-of-field and refined-boundary cases;
option-time geometry; exposure-end line of sight; and slew plus settling time. A replay test
generates the same 24-hour window output twice from pinned files and fails if the public-address
check is reached. The independent Astropy geometry comparison checks 20 generated options.

The focused command `pytest -q tests/unit/test_orbit_engine.py
tests/unit/test_geometry_cross_validation.py tests/unit/test_orbit_capacity.py` completed with
**14 tests passed**. After the final artifact-status metadata update, the capacity unit test was
rerun and **1 test passed**. Ruff check and format check also passed for the orbit package, orbit
tests and candidate builder.

No repository-wide test result is claimed here.

## Capacity result: synthetic base sources

The artifact contains 1,469 windows, 88 feasible windows, and six spacecraft/pass groups with at
least one feasible selected-source window during the 72-hour horizon. There are 58 spacecraft/pass
labels across all rows; the other 52 contain no feasible selected-source window and are not counted
as capacity-bearing regional passes. Capacity was optimized independently for each of the six
feasible groups with the production CP-SAT scheduler and equal positive integer utility per
window, so the objective maximizes scheduled acquisition count. Every solve returned `OPTIMAL`.

| Spacecraft / orbit pass | Feasible source windows | Candidate options | Scheduled acquisitions | Independent checker |
|---|---:|---:|---:|---|
| `vsat_a:26` | 9 | 89 | 8 | Pass; zero violations |
| `vsat_a:41` | 20 | 240 | 10 | Pass; zero violations |
| `vsat_b:11` | 20 | 220 | 10 | Pass; zero violations |
| `vsat_c:13` | 5 | 36 | 5 | Pass; zero violations |
| `vsat_c:28` | 20 | 240 | 10 | Pass; zero violations |
| `vsat_c:43` | 14 | 140 | 10 | Pass; zero violations |

This meets the registered G1-F thresholds for the synthetic base source set: six feasible regional
passes (threshold at least five), with at least five scheduled acquisitions in each (threshold at
least four). The result applies to independent single-pass solves. Cross-pass resource coupling is
not modeled, so the six counts must not be summed and reported as a feasible 72-hour throughput.
The geometric throughput proxy remains diagnostic only; it is not a capacity gate result.

Codex-3 independently reconstructed every selected option, ran the independent checker on each
pass, and reran each capacity optimization. It confirmed all six stored counts, `OPTIMAL` solver
status, zero checker violations, matching input/code hashes and the G1-F summary on the final
artifact SHA. The final artifact's `window_provenance` points to the previously reviewed candidate
from which the serialized windows were reused. Golden promotion remains with the verification owner.

## Historical-location candidate

The builder accepts an explicit pinned source set so the same capacity method can be applied to the
20-record Codex-1 sample. Source placement used only native ID, acquisition time and coordinates.
Emission rates, uncertainties and raster values did not affect orbit geometry, and historical
detections are not treated as current activity or truth. Its source input is historical location
context only. The candidate records hashes for each selected metadata/raster file; raster hashes
are lineage evidence only, because no raster values were used.

The selected records came from Codex-1's inventory (SHA-256
`c7f591ad79fd1f33fad2d30ffc0225642730d038ccfeeac6cb28c31fad24ff74`). A normalized, pinned dataset
manifest is still pending the shared contract integration; authentic retrieval time/URL provenance
is unknown and has not been inferred from filenames or filesystem times. The source set contains
20 selected records (10 numeric-rate and 10 missing-rate) and no uniform-fill locations. Its source
set SHA-256 is `0c1eedce6509396d31fb1235e53b5a5f2065a3286bb608b6cdfb541f6dac6b54`. The candidate
`data/fixtures/windows_permian_sample_candidate.json` has SHA-256
`44f83cf6f5dacf518ca842dda2a284065979cdf9bef4357e95f992dc3bcf0da0` and records the inventory,
input-file, configuration, ephemeris/EOP and code hashes.

The artifact contains 1,494 windows, 92 feasible windows and seven spacecraft/pass groups with at
least one feasible selected-source window. Each pass solve returned `OPTIMAL` and the local
independent checker reported zero violations.

| Spacecraft / orbit pass | Feasible source windows | Candidate options | Scheduled acquisitions | Local checker |
|---|---:|---:|---:|---|
| `vsat_a:26` | 13 | 139 | 9 | Pass; zero violations |
| `vsat_a:41` | 20 | 240 | 10 | Pass; zero violations |
| `vsat_b:11` | 20 | 214 | 9 | Pass; zero violations |
| `vsat_c:13` | 8 | 55 | 6 | Pass; zero violations |
| `vsat_c:28` | 20 | 240 | 10 | Pass; zero violations |
| `vsat_c:43` | 9 | 87 | 8 | Pass; zero violations |
| `vsat_d:13` | 2 | 12 | 2 | Pass; zero violations |

This sample meets the ≥5-pass count but **fails G1-F capacity** because its minimum is 2, below
the registered ≥4 acquisitions per pass. No registered parameter or scenario value was changed in
response. Codex-3 independently confirmed the source-set reconstruction, all selected-file hashes,
all seven zero-violation checker results and all seven OPTIMAL capacity counts against the final
artifact SHA. The final artifact's `window_provenance` points to the previously reviewed candidate
from which the serialized windows were reused. Until the normalized manifest is available, this
remains provisional historical-location evidence rather than final integrated-source evidence. The
candidate remains pending the verification owner's golden-artifact decision.

## Capacity method and limits

For each feasible spacecraft/orbit pass, the builder runs `aether.planning.cpsat.solve_schedule`
over the actual acquisition options. The scheduler enforces one option per window, temporal and
slew conflicts, source-visit limits, per-orbit acquisition and storage limits, and battery energy
constraints. The selected schedule is checked with `aether.planning.checker.check_schedule`.
Codex-3's review reconstructed the same selections and independently recomputed geometry and slew;
the checker imports neither the production orbit helper nor the optimizer/policy modules.

Each pass solve starts from its configured resource state. The measurement therefore shows
schedule-constrained capacity within a pass, not a continuous cross-pass plan with carried state,
downlink, or cross-pass source visits. It makes no policy-performance claim. No registered orbit,
sensor, resource or horizon parameter was changed.
