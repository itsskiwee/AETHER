# AETHER hackathon submission

## Submission details — complete before submitting

- **Competition / event:** [COMPLETE: competition name]
- **Track / category:** [COMPLETE]
- **Team name:** [COMPLETE]
- **Team members and roles:** [COMPLETE]
- **Submission deadline and time zone:** [COMPLETE]
- **Official length or format limit:** [CHECK RULES AND COMPLETE]
- **Recorded demo URL:** [COMPLETE AFTER RECORDING]
- **Repository or project URL:** [COMPLETE]

## Project description

AETHER is a research prototype for planning which methane-source hypotheses simulated Earth-observation satellites should observe next. It compares a largest-first scheduler with an adaptive expected-information-gain planner, records how simulated evidence and refreshed forecasts affect plans, and presents the resulting runs in a reproducible, offline console.

## Problem

Satellite observation opportunities are intermittent and constrained by visibility, sensor conditions, weather, and spacecraft resources. Choosing only the source with the largest current estimate can overlook uncertainty and the value of a future observation. A planner also needs to distinguish a valid non-detection from an invalid or missing observation so that missing evidence is not treated as proof of no emissions.

## Approach

AETHER runs a seeded simulation with synthetic source hypotheses, hidden simulated ground truth, virtual spacecraft, synthetic weather, and modeled acquisition outcomes. The planner sees its model and forecast inputs; the evaluator uses hidden truth for scoring. The demo runs `largest_first` and `adaptive_eig` under the same `configs/demo.yaml` scenario and seed 1000. A separate development comparison uses `configs/base.yaml`, which excludes the demo's scripted forecast event.

## Implemented features and observed run counts

The read-only console presents recorded spacecraft windows and feasibility reasons, plan revisions and candidate utilities, an independent schedule-check result, source belief histories and evidence, forecast events, evaluator output, and method and provenance details. The records can be replayed without rerunning the simulation. Both seed-1000 run archives contain 20 synthetic source hypotheses and 1,483 generated windows.

| Demo policy (`configs/demo.yaml`, seed 1000) | Plans / independent checks | Checker violations | Acquisitions and outcomes |
|---|---:|---:|---|
| `largest_first` | 40 / 40 | 0 | 35: 12 detections, 9 valid non-detections, 14 invalid acquisitions |
| `adaptive_eig` | 52 / 52 | 0 | 47: 10 detections, 23 valid non-detections, 14 invalid acquisitions |

The event at simulation hour 20 refreshes forecasts at `2026-10-17T20:00:00Z`. In `largest_first`, forecast revision 10 retains the same selections. In `adaptive_eig`, revision 11 changes selections: the candidate set remains 16 windows, with 11 option IDs removed and 9 added compared with the preceding plan. The forecast issuance advances from hour 18 to hour 20 and refreshes estimates for other sources. The event targets `source-001`, which has no feasible observation window during the scripted cloud interval from simulation hours 20–32. This is evidence of a recorded selection change after refreshed forecasts; it does not show that the planner avoided observing the targeted source during that interval.

The separate base-config comparison contains six actual runs: three policies (`largest_first`, `adaptive_eig`, and `greedy_eig`) on development seeds 1000 and 1001. All six runs have zero checker violations and no rejected proposals. The comparison has two paired samples per policy comparison and is labeled preliminary with insufficient samples. These two seeds do not establish adaptive superiority, and the comparison is not a holdout evaluation.

## Simulation and offline status

This is a **SIMULATED MISSION — offline replay**. The demo uses seeded synthetic sources, hidden synthetic truth, virtual spacecraft, modeled sensor outcomes, and synthetic weather. Its EMIT-shaped ingestion fixture is synthetic; these runs do not depend on verified real plume records. AETHER does not task real spacecraft or establish real-world emissions, source attribution, or emission reductions.

Once dependencies and the repository's pinned ephemeris data are installed, simulation generation and console replay run offline and require no credentials. Initial dependency installation needs access to package registries. The console replays actual saved run records; it does not present replay as a live satellite tasking system.

## Limitations

These results depend on the simulator's explicit assumptions about sources, weather, sensors, and spacecraft. The scripted forecast event demonstrates a logged forecast refresh and, for `adaptive_eig`, a different recorded selection. Because the targeted source has no feasible window in the affected interval, it does not demonstrate targeted cloud avoidance. The development comparison uses only two seeds, has no locked protocol or holdout result, and is too small to support a superiority claim. The prototype does not validate operational mission capability or real-world methane attribution.

## Supporting project material

- [Repository overview](../README.md)
- [Offline console walkthrough and known-good evidence](demo-console.md)
- [Development comparison and interpretation](demo-comparison.md)
- [Acceptance record](../runs/demo/acceptance.json)
