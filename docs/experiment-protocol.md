# AETHER — Experiment Protocol Procedure (L3)

The protocol itself is `experiments/protocol.yaml`. This page describes how it is used, so that a
holdout result means something.

## Order of operations

1. **Tuning.** Run anything on `experiments/seeds_dev.txt`. Results are labelled "Tuning-seed
   results; not a pre-registered test."
2. **Gate G4.5.** Run `random_feasible` and `oracle` on the tuning seeds and record the verdict in
   `docs/validation-report.md` §3. If it fails, change the **scenario** (sources, capacity,
   horizon), never the planner.
3. **Fix open inputs.** The user approved a minimum absolute paired Brier difference of **0.01**
   for the 80% power seed-count rule on 17 Oct 2026. Once tuning-seed SD is available, calculate and
   report the required holdout count (capped at the pre-registered budget of 100). Settle any metric
   decision in validation-report §1.1 that a reviewer wants changed before locking.
4. **Lock.** Set `locked: true`, commit `experiments/protocol.yaml`, then tag that commit
   (for example `git tag protocol-v1-locked`). Only the user or L1 commits.
5. **Holdout.** `benchmark(protocol, experiments/seeds_holdout.txt, out_dir)` now runs.
6. **Report every family**, including ones where `adaptive_eig` ties or loses.

## What the code enforces (`aether.evaluation.protocol.check_seed_access`)

| Condition | Result |
|---|---|
| Seed file is the tuning list | allowed, no lock needed |
| Seed file is neither list | refused |
| Tuning and holdout lists overlap | refused |
| Holdout, `locked: false` | refused |
| Holdout, protocol has uncommitted edits or is untracked | refused |
| Holdout, no git tag contains the last commit that touched the protocol | refused, including when the file was edited **after** tagging |
| Holdout, locked, committed and tagged | allowed; the tag name is written into the results JSON |

Every results JSON also records the protocol SHA-256, the seed-file SHA-256 and the model/truth
config hash of every family.
