# Offline development comparison

This is a **SIMULATED MISSION** using an offline, reproducible simulation. It is a preliminary development comparison, not a validated research benchmark or evidence of operational performance.

From the repository root, after installing the backend dependencies:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m aether.evaluation.development \
  --output-dir runs/demo/benchmark --seeds 1000,1001
```

The command runs `largest_first`, `adaptive_eig`, and `greedy_eig` using **configs/base.yaml**, without the scripted forecast injection in `configs/demo.yaml`. Requested seeds must be unique members of the existing development seed list. It never locks the protocol or runs holdout seeds. Run one seed first and inspect `development-timing.json` before selecting a larger batch. For example, `--seeds 1000,1001` requests two approved development seeds.

Outputs are generated under the requested directory, which is ignored by Git:

- Each `<run_id>/run.json` is an actual runner record, round-tripped through the nested `RunRecord` contract before saving.
- `benchmark-runs.csv` contains evaluator scores for each policy and seed, with acquisition, denominator, and checker accounting.
- `benchmark-results.csv` aggregates evaluator scores and reports sample counts and undefined values.
- `benchmark-confidence-intervals.json` compares adaptive EIG with both largest first and greedy EIG. Differences are adaptive minus comparator. Lower Brier is better; higher recall is better. At least two defined pairs are required to compute a paired bootstrap interval (PR-E04); fewer than ten pairs are explicitly labeled **insufficient samples**. All results remain preliminary and no research success verdict is issued for this single-family exercise.
- `development-timing.json` records measured elapsed wall time for each complete policy run and the comparison. This sidecar is nondeterministic. It does not claim to measure solver-only performance. Missing solver runtime remains null in evaluator output.

The console's comparison view reads the evaluator CSV and confidence interval artifacts. The demo's scripted forecast revision is demonstrated separately using `configs/demo.yaml`; do not pool those scripted runs into this comparison.

The full registered benchmark still requires the remaining families, the discriminability and calibration gates, an explicitly authorized protocol lock, and holdout validation. A small development comparison cannot establish policy superiority.

The complete development pilot on seed 1000 finished in **395.771 seconds** of measured wall time (about 6.6 minutes), including three policy runs and evaluator output. Based on that measured cost, the packaged demonstration uses two development seeds, **1000 and 1001**, to exercise paired interval computation while keeping the generation cost manageable. Two seeds remain **insufficient samples**, and all comparisons remain preliminary. The main `scripts/demo.sh` command runs this batch after verifying deterministic replay.

The actual pilot artifacts are retained at `runs/demo-pilot-final/benchmark/`. Its evaluator Brier scores were 0.202736 for largest first, 0.209555 for adaptive EIG, and 0.239856 for greedy EIG. Lower is better: adaptive EIG had a higher Brier score than largest first on this single development seed. This is a descriptive result, with no uncertainty interval available from one seed and no superiority claim. Every pilot run had zero recorded independent checker violations and was reloaded through `RunRecord`.

The earlier interrupted pilots under `runs/demo-fixed/` are diagnostic artifacts from before the final geometry repairs. They are not the known-good artifact set and must not be used for presentation or scientific comparison. The completed final two-seed artifact set is `runs/demo/benchmark/`. It contains six actual runs with zero checker violations and took 631.763 seconds of measured complete-comparison wall time. The report records two pairs for each displayed interval, labels the results preliminary and insufficient samples, and records no protocol verdict.


For Brier, the final evaluator reports adaptive minus largest-first mean difference
+0.00429953, with descriptive 95% bootstrap interval [0.00178077, 0.00681829]. Adaptive
minus greedy EIG is -0.01121558, interval [-0.03030178, 0.00787062]. These are the
evaluator's recorded two-seed summaries; they do not establish superiority. The
browser displays the recorded values and suppresses an interval interpretation
below ten pairs. The final unmocked browser smoke checked these displayed intervals
against the actual report.
