# AETHER hackathon submission

## Project description

AETHER is a reproducible research prototype for planning which methane-source hypotheses virtual Earth-observation satellites should observe next. It connects real historical NASA EMIT plume locations to simulated orbital opportunities, sensor outcomes and an adaptive information-gain planner. A read-only console shows what was scheduled, why, which constraints were checked, and how the simulated evidence changes the model.

## Problem and approach

Satellite observation opportunities are intermittent and constrained by geometry, weather, sensor validity and spacecraft resources. A large estimated source is not always the most informative next observation. AETHER compares a largest-first policy with an adaptive expected-information-gain policy using the same source locations and windows. An independent checker validates the selected schedules. Missing or invalid observations remain distinct from valid non-detections.

## What is working

The checked-in demonstration uses twenty historical EMIT V002 Permian plume records to place twenty virtual source hypotheses, with no uniform-fill locations. Every selected metadata/raster pair and the normalized observations are hash-pinned. Historical rates do not set simulated truth or establish present activity. Ten sample records have unquantified rates, preserved as null; the unknown original retrieval time is also preserved as null.

Both policies run over the same 1,494 generated windows, with seed 1000:

| Policy | Plans / independent validations | Acquisitions | Checker violations |
|---|---:|---:|---:|
| adaptive_eig | 47 / 47 | 51 | 0 |
| largest_first | 41 / 41 | 37 | 0 |

The accepted records have byte-identical replay and verified export reloads. Each input manifest enumerates 46 input files, including 42 pinned dataset files. Measured performance is stored separately from deterministic simulation records.

The console and artifact API now run from one server. A saved demonstration is checked into `data/fixtures/hosted_replay`, so reviewers can open the product without regenerating the simulations. The Dockerfile and native commands are documented in `docs/hosted-replay.md`.

## Three-minute demonstration

1. Start the saved replay with the README commands and open the console. Explain the SIMULATED MISSION label and historical versus simulated provenance.
2. Open historical EMIT context: show dates, sample lineage, source hashes and a null-rate record.
3. Select adaptive_eig and inspect windows, candidate utilities, plan revisions and independent validations.
4. Open a source history and distinguish detection, valid non-detection and invalid acquisition. Show an evidence-driven revision in the planner view.
5. Open largest_first and compare recorded scheduling choices. Acquisition counts alone do not establish scientific superiority.
6. Finish with method/input hashes and the acceptance record. The forecast event at hour 20 is logged but changes no selected option in this pinned demo; do not describe it as demonstrated forecast-driven selection change.

## Scientific status and limitations

This is a simulated mission and recorded replay. The spacecraft, weather, sensor responses, acquisitions and ground truth are simulated. AETHER does not command real satellites, measure current emissions, establish source attribution or verify reductions.

Implementation and demonstration evidence are available; scientific acceptance is unfinished. The integrated capacity scenario fails its minimum on one pass (two acquisitions against a required four). The synthetic thirty-seed discriminability pilot failed. Pinned-data gate/calibration work is separate from this fixed replay sample; use the final validation report for its latest status. The protocol remains unlocked and no holdout result or adaptive superiority is claimed by this submission draft. The comparison panel reports unavailable when completed evaluator artifacts have not been supplied.

## Submission material

- Repository: https://github.com/itsskiwee/AETHER (the team manages public visibility and the submitted branch).
- Startup and product overview: [README](../README.md).
- Hosted/native replay: [deployment guide](hosted-replay.md).
- Walkthrough: [console guide](demo-console.md).
- Requirements and evidence: [P0 matrix](p0-requirements-evidence.md).
- Accepted saved sample: [acceptance record](../data/fixtures/hosted_replay/acceptance.json).
- Data provenance and attribution: [dataset interface](dataset-interface.md), [data licenses](../DATA_LICENSES.md), [citations](../CITATIONS.md).

Add the actual hosted URL and recorded-demo URL after those artifacts exist. Do not submit a local loopback URL as a hosted website.
