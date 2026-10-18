# AETHER — Validation Report (L3)

## Current status — integrated pinned-data build (18 Oct 2026)

The base scenario now places its 20 source hypotheses at 20 pinned historical EMIT V002 Permian plume locations, with 0 uniform fill (`configs/base.yaml`, PR-P04). Every result below uses that scenario unless it is labelled synthetic-only. **Implementation is integrated; scientific acceptance is not complete.**

| Item | Result | Section |
|---|---|---|
| G1-F capacity, integrated scenario | **FAIL**: 7 passes ✓; one pass with at most 2 acquisitions ✗ (minimum 4) | §6, `docs/orbit-model-report.md` |
| G4.5, synthetic-only m0 pilot (C2-06) | **FAIL** (gap 0.0048 vs 2 SD 0.0441) | §3.1 |
| G4.5, pinned data, six families, 30 tuning seeds | **FAIL in all six** (gaps −0.0004 to 0.0026 vs 2 SD 0.0179–0.0259; 0 checker violations) | §3.2 |
| SCI-10 calibration, m0 pinned | random_feasible (30 seeds): **meets** the criteria (weak test). adaptive_eig (5 seeds): coverage meets; reliability rule **fails** as written (two 9-point bins) | §3.3 |
| Power calculation, lock, holdout | **Not run**: blocked by the G4.5 scenario decision | §6 |

The old two-seed demo comparison (17 Oct, synthetic placement) stays below as history. It is not a result for the pinned scenario.

## Historical: offline demo delivery (17 Oct 2026, synthetic-only placement)

Preserved in the original `AETHER` checkout, `runs/demo`. It predates the pinned dataset.

Owner: L3 (Evaluation & integrity). Code: `backend/aether/evaluation/`.

The offline delivery acceptance is complete for the documented demo scope. The actual
`configs/demo.yaml`, seed-1000 records contain 40 plans, 40 validation records, and 35 acquisitions
for `largest_first`, and 52 plans, 52 validation records, and 47 acquisitions for `adaptive_eig`.
Both have zero checker violations. `runs/demo/acceptance.json` records byte-identical separate-
process replay, verified export reloads, outcome counts, and the hour-20 forecast revision evidence.
The adaptive record changes selected option IDs after the forecast revision; largest-first retains
its selections. This is demonstration evidence for the recorded event and plans.

The recorded backend suite passed **294 tests**. The production frontend build succeeded, and the
final browser suite passed **13 tests**, including actual artifact/API replay; the documented fresh
backend installation passed all 14 API tests. See `docs/demo-console.md` for the walkthrough.

The actual base-config development comparison contains six records for one family
(`m0_well_specified`), three policies, and seeds 1000 and 1001. Its interval artifact records two
pairs, marks the results preliminary and insufficient for research claims, and has
`success_verdict: null`. `experiments/protocol.yaml` remains unlocked and no holdout validation was
run. These results do not establish scientific gate completion. Artifacts are in
`runs/demo/benchmark/`.

## Historical pre-delivery findings — 17 Oct 2026, superseded for delivery status

An earlier real-runner smoke failed on a candidate at 40.002881° against the configured 40° limit;
one attempt wrote no run artifact. An intermediate integration snapshot also recorded pointing and
slew checker violations. The same pre-delivery period recorded a TestClient hang at
`/api/runs/run-a` and no runner-backed benchmark output. Those findings described the earlier
working tree. The accepted RunRecords, current API/browser replay, and final test logs above
supersede them for offline delivery status.

The implementation notes attributed the boundary failures to midpoint transition estimates,
UT1/UTC handling in the independent checker, unavailable pinned polar-motion data, and using
exposure-start rather than exposure-end LOS for planner slew. These corrections support the final
artifact checks; they do not establish science or holdout validation. The checker continues to
propagate independently and performs its own Astropy transforms. A seed-1000 boundary regression
checks the options in the problematic pass; the UTC correction follows the
[official Astropy satellite recipe](https://docs.astropy.org/en/stable/coordinates/satellites.html).

---

## 1. Metric definitions (EVL-01, EVL-02)

| Metric | Definition | Direction | Undefined when |
|---|---|---|---|
| `brier_active_state` | mean (p_active − z_true)² over every (source, evaluation time) | lower | no points |
| `log_loss_active_state` | mean −[z ln p + (1−z) ln(1−p)], nats, p clipped at PR-E08 | lower | no points |
| `ece_active_state` | Σ_b (n_b/N)·\|mean p − mean z\|, 10 equal-width bins (PR-E09) | lower | no points |
| `flux_interval_coverage_90` | share of (source, time) pairs whose `flux_ci90_kg_h` contains the true static flux Q_i | close to 0.90 | no points |
| `time_to_corroboration_hours` | restricted mean of first time P(Z = z_true) ≥ 0.90 (PR-E03); censored sources count as the horizon | lower | no sources |
| `corroborated_sources`, `censored_sources` | counts behind the line above | — | never |
| `high_impact_recall_at_5` | \|top-5 ∩ high-impact\| / \|high-impact\| at the last evaluation time (PR-E02, PR-E10) | higher | seed has no high-impact source (excluded, counted) |
| `valid_acquisition_fraction` | (DETECTION + VALID_NON_DETECTION) / attempted acquisitions | — | no acquisitions |
| `solver_runtime_p95_s` | 95th percentile of measured `policy.plan` wall time (model build + solve), reported as `policy_plan_wall_p95_s` in `benchmark-performance.csv` from the runner's separate `RunPerformance` artifact (PERF-01). The deterministic score column stays empty because `Plan.runtime_s` is None by design. Measured values depend on machine and load and are not reproducible | lower | run has no measured performance (reported as `measured=False`, never 0) |
| `feasibility_checker_violations` | total violations across all validations; must be **0** | — | never |
| `plans_without_validation` | plans with no checker record; must be **0** | — | never |

Breakdowns: `[regime=<R>]` uses the **true** regime. `[observed=yes|no]` splits on whether the run
made at least one evidence-bearing acquisition of the source. Every breakdown reports
`n_points` and `n_sources`.

### 1.1 Decisions taken, with alternatives (review requested)

`CLAUDE.md` asks L3 to record judgment calls instead of making them silently. Each row is the
current default. A reviewer can change any of them **before** the protocol is locked, never after.

| # | Question | Chosen | Alternatives | Why chosen |
|---|---|---|---|---|
| D1 | Evaluation times | t0 + 6k h for 6k < horizon (t0 included, horizon excluded) | exclude t0, since every policy has the same prior there | Literal reading of PR-E01. Truth has no cell at the horizon. Including t0 adds the same constant to every policy, so paired differences are unchanged. |
| D2 | Missing snapshot at an evaluation time | **raise** | carry the last snapshot forward | A stale belief would score a policy on information it didn't have. A runner bug should fail loudly. |
| D3 | Flux-coverage target | static Q_i (`median_flux_kg_h`) at every evaluation time, active or not | only while truly active; against hourly q[t] | The belief's flux variable is Q_i (L2 confirmed, see `model-card-source-state.md`). q[t] includes hourly noise the belief does not model as a state. |
| D4 | High-impact ranking score | Σ_r P(r)·π_r·median Q (model π_r) | p_active(final)·median; posterior mean E[Q]·p_active | PR-E02 thresholds a long-run mean rate, so the ranking should estimate the same quantity. The instantaneous p_active mostly reflects the last pass. |
| D5 | Corroboration summary | restricted mean (censored = horizon) plus counts | Kaplan–Meier median; mean over corroborated sources only | One finite number per run that never drops censored sources (EVL-02). KM median is often undefined with few events. |
| D6 | "Observed" | ≥ 1 DETECTION or VALID_NON_DETECTION | any attempted acquisition | INVALID/NOT_OBSERVED carry no emission evidence (AGENTS rule 3). |
| D7 | Bootstrap p-value (for Holm) | two-sided percentile-bootstrap p with +1 correction | paired t-test p; Wilcoxon signed-rank | Same resampling distribution as the reported CI, so a CI and its Holm decision can't disagree for method reasons. |
| D8 | Bootstrap stream | `keyed_rng(protocol_version, "bootstrap", "<family>\|<metric>\|<a>-<b>")` | — | Reproducible, and independent of the order comparisons run. |
| D9 | G4.5 family scope (Claude-2, 18 Oct 2026; **needs human sign-off at the gate**) | Evaluate the gate in **all six protocol families** on all 30 tuning seeds. G4.5 passes only if every family passes; each family's verdict is reported | (i) m0 only, since the gate tests the scenario and m0 is the control; (ii) m0 plus at least 2 of m1–m4, mirroring the success criterion | The success criterion draws on m0 and on m1–m4 under Holm. A family where even the oracle-informed reference can't separate from random can't contribute a meaningful win or loss, so it would dilute Holm without informing it. Running all six costs only 360 reference runs. If only some families fail, the report names them and Claude-2 proposes a scenario change for review; no family is dropped silently. h168 is not a protocol family and is not gated. |
| D10 | SCI-10 calibration inference | Seed-cluster percentile bootstrap (whole seeds resampled; 2,000 resamples, stream `keyed_rng(0, "bootstrap", "calibration", label)`) for coverage and reliability-bin residuals | Point-level binomial intervals | Points within a run share sources and are autocorrelated over 6 h steps. Point-level intervals would be far too narrow. |

**Caveat on the `[observed=…]` breakdown.** Which sources get observed depends on the policy, so
the subsets differ between policies. Treat the breakdown as descriptive and never as the primary
comparison.

## 2. Statistics (EVL-03)

- Paired by seed within family. The difference is `a − b`; negative favours `a` for Brier.
- Percentile bootstrap, 10 000 resamples, 95% (PR-E04). Fewer than 2 defined pairs →
  "insufficient samples", no CI.
- Holm–Bonferroni across m1–m4 at family-wise α = 0.05. m0 needs its CI to lie below 0.
- Coverage test: with a known effect at n = 30 seeds over 200 trials, the 95% CI's coverage lies in
  [0.89, 0.99] (`test_bootstrap_ci_covers_true_difference_about_95_percent`). The percentile
  bootstrap under-covers slightly at small n. That's one more reason not to trust a single
  marginal family.

## 3. Discriminability gate G4.5 (EVL-08): FAILS (synthetic pilot and pinned data); scenario decision pending

Rule as written in `protocol.yaml`: mean(random − oracle Brier) > 2 × **SD** of the per-seed paired
difference on the 30 tuning seeds. Family scope: D9 (all six protocol families must pass).

**Procedure.** `python -m aether.evaluation.gate --repo . --output-dir runs/gate --workers N` runs
`oracle` and `random_feasible` for each family × tuning seed through the runner (`run_policy`, the
dataset named by the config, no explicit plume input). It refuses the holdout list. It writes:

- `gate.json`: per-family verdict, gap, SD, SE (for information only), number of seeds where the
  oracle is better, mean Brier per reference, capacity summary (passes, passes per 72 h,
  acquisitions per pass, capacity/demand from the `random_feasible` runs), reference-run checker
  violations, protocol and seed-file SHA-256, config hashes, `RunRecord.input_dataset` references,
  git commit and dirty paths, and machine information;
- `gate-seeds.csv`: per-seed paired values;
- `records/<family>/<policy>/<seed>.json`: compact per-run scores, capacity and calibration points.
  A rerun reuses a record only when its config hashes, code version, policy and seed all match;
- `timing.jsonl`: measured wall time per run (nondeterministic sidecar, never in RunRecords).

A pilot on the pre-wiring, synthetic-placement scenario is labelled as such and is superseded by the
run on the wired scenario. **Defect found by the pilot (18 Oct 2026, fixed in C2-04):** `OraclePolicy`
called `greedy_insert` without `now_utc`, so completed acquisitions counted against the per-solve
source cap (PR-O03). The oracle could look at each source only once per run (exactly 20
acquisitions per seed, against random's 32–36). Every oracle result before C2-04 is invalid and was
discarded. `test_oracle_can_revisit_a_source_observed_in_an_earlier_solve` guards it. **Order:** gate on the wired dataset → power calculation → lock.

### 3.1 Pilot result: synthetic-only m0, 30 tuning seeds (18 Oct 2026). **FAIL**

Pre-wiring scenario (`plume_dataset: null`, all 20 sources seeded uniform fill), code `18a74f4`
(clean tree), oracle fix C2-04 included. Artifacts: `experiments/results/g45-pilot-synthetic-m0/`
(`gate.json`, `gate-seeds.csv`). The wired-dataset run supersedes this; it is reported because it
already decides the scenario question below.

| Quantity | Value |
|---|---|
| mean(random − oracle Brier) | **0.0048** |
| SD of the paired difference (rule: gap > 2 SD = 0.0441) | 0.0221 |
| SE (information only) | 0.0040 |
| Seeds where the oracle reference beats random | **15 / 30** |
| Mean Brier, oracle / random | 0.2040 / 0.2087 |
| Passes per 72 h (random reference runs) | 6.6 (6–7) |
| Executed acquisitions per pass | 5.7 (4.6–6.8) |
| Capacity/demand | 0.28 (0.23–0.34) |
| Brier gain over the no-observation baseline (stationary prior p = 0.291 at every point) | oracle 0.013, random 0.008 |
| Checker violations in the 60 reference runs | 0 |

**Interpretation.** Under this scenario, observing at all improves the primary metric by about 0.01
Brier points. That is the size of the registered minimum effect. Even an oracle-informed greedy
reference can't separate from random on half the seeds. Likely causes, each visible in the data:

- only about 6.6 passes per 72 h;
- evaluation every 6 h, while INTERMITTENT and EPISODIC states change on a 3–24 h scale, so one look
  says little about the next evaluation point;
- about one quarter of the flux prior lies below the VS-A Q50 at median wind, where a look at an
  active source mostly returns a valid non-detection.

The benchmark as configured would compare policies inside a range of about 0.01 and would almost
certainly report no difference whatever the planner did. That is the situation G4.5 is meant to stop.

**This is a scenario finding, not a model defect.** The model is well specified, every source
starts at the stationary prior, and the updated belief improves on the prior on average. The
reference is weak in one respect, recorded here rather than fixed: its value p_valid·(p − z)²
ignores detectability. A detectability-aware reference would bound headroom better, but changing the
reference after seeing a fail risks gate-shopping. Any such change needs explicit approval and must
be reported together with this result.

**Options (Work_Plan: "If it fails, resize the scenario … never tune the planner"; human decision):**

| Option | What changes | Evidence / cost |
|---|---|---|
| A. Make `h168_long_horizon` (168 h, 60 sources) the benchmark base | horizon, source count | More passes for regime learning; 3× sources lowers per-seed SD. A 10-seed diagnostic was proposed, but no h168 gate output exists in any worktree (checked 18 Oct, 09:20 EDT), so its outcome is **unknown**. Runs cost about 5–8× more |
| B. More passes: denser virtual constellation (more spacecraft/planes) | `configs/spacecraft`, base | Directly raises information per evaluation interval; changes G1-F evidence and orbit artifacts |
| C. Evaluate at pass times or hourly instead of every 6 h (PR-E01) | metric definition | Measures what observation can know. It is a metric change, which must be decided before lock and must not be chosen for being favourable |
| D. Keep the scenario and accept a likely null | none | Honest but uninformative; power would need far more than 100 seeds |

Claude-2 recommendation (written before the diagnostic; it never produced output): wait for the h168 diagnostic. If it passes, adopt **A** (already a
registered family, smallest conceptual change). Otherwise combine A with B. C and D are not
recommended.

Notes for the reviewer:

1. **The rule uses SD, not standard error.** It asks that the oracle beat random on almost every
   seed, which is much stricter than "the mean gap is significant". I implemented it as written
   (`test_gate_rule_uses_sd_not_se`). If the intent was SE, change it before locking.
2. **The oracle is a greedy reference, not a proven bound.** `OraclePolicy` knows z_true at each
   option time and ranks windows by p_valid × (p_now − z_true)², but it plans myopically through
   the same greedy insertion as the baselines. A smarter policy could in principle beat it. Report
   it as "oracle-informed greedy reference".
3. Capacity/demand is reported per tuning seed as acquisitions / (sources × passes). A ratio near
   1 means the policies can differ only in ordering. Acquisitions per pass here are **executed**
   acquisitions in the random reference runs. G1-F's "feasible acquisitions per pass" is Codex-2's
   orbit evidence, independently confirmed by Codex-3, and these numbers don't replace it.
4. **Seed-count procedure:** `seed_count_rule` uses the approved **minimum effect** (absolute paired
   Brier difference). The user approved **0.01 Brier points** for 80% power on 17 Oct 2026; this is
   now recorded in the still-unlocked protocol. `stats.seeds_for_power(sd, min_effect)` computes
   the required count from the tuning-seed paired SD of the **primary comparison**
   (adaptive_eig − largest_first) per family. The binding family is the one with the largest SD. If
   the requirement exceeds the default budget of 100, the report says so and the decision goes to
   the user before lock. It is never silently capped.
5. If the gate fails, the remedy is a registered **scenario** change (sources, capacity, horizon)
   proposed for human review (Work_Plan G4.5 is "L3 + human"). The planner is never tuned to pass.

### 3.2 Pinned-data gate: six protocol families × 30 tuning seeds (18 Oct 2026). **FAIL**

Scenario: `configs/base.yaml` with the pinned EMIT manifest (20 plume-seeded sources, 0 fill) and each protocol family override. 360 reference runs (oracle-informed greedy reference and random_feasible). Commit `272aba5`, clean tree, code identity `c79062f5…`. Command: `python -m aether.evaluation.gate --repo .. --output-dir ../runs/gate-pinned --workers 9`, with `AETHER_WINDOW_CACHE_DIR` set. Artifacts: `experiments/results/g45-pinned-dev/` (`gate.json`, `gate-seeds.csv`, `timing.jsonl`). The rule is applied as registered: SD, not SE.

| Family | Gap mean(random − oracle) | SD paired | 2 SD threshold | SE (info) | Oracle better | Mean Brier oracle / random | Passes/72 h | Acq./pass (executed) | Capacity/demand | Checker violations | Verdict |
|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|
| m0_well_specified | 0.0025 | 0.0128 | 0.0256 | 0.0023 | 17/30 | 0.1955 / 0.1980 | 7.0 | 5.35 | 0.267 | 0 | **FAIL** |
| m1_persistence_wrong | 0.0001 | 0.0090 | 0.0179 | 0.0016 | 14/30 | 0.1584 / 0.1585 | 7.0 | 5.35 | 0.267 | 0 | **FAIL** |
| m2_pod_optimistic | 0.0010 | 0.0109 | 0.0219 | 0.0020 | 15/30 | 0.2005 / 0.2015 | 7.0 | 5.35 | 0.267 | 0 | **FAIL** |
| m3_forecast_overconfident | -0.0004 | 0.0123 | 0.0246 | 0.0022 | 15/30 | 0.1984 / 0.1980 | 7.0 | 5.35 | 0.267 | 0 | **FAIL** |
| m4_false_positives | 0.0021 | 0.0130 | 0.0259 | 0.0024 | 17/30 | 0.1965 / 0.1986 | 7.0 | 5.35 | 0.267 | 0 | **FAIL** |
| r1_resource_scarce | 0.0026 | 0.0107 | 0.0215 | 0.0020 | 16/30 | 0.2031 / 0.2058 | 7.0 | 2.47 | 0.124 | 0 | **FAIL** |

Overall: **FAIL in all six families** (D9 scope; m0 alone also fails). Reference checker violations: 0 in all 360 runs. The SE column is information only. Wall time: 72 min for 360 runs on 9 workers; per run 17.4–796.9 s, median 88.0 s. The maximum is r1's cold geometry, because r1 changes spacecraft storage and therefore the window key.

**Interpretation.** The pinned scenario reproduces the synthetic pilot's finding in every family. Within the 72 h horizon, a reference that knows the true state at each option time gains almost nothing over random feasible looks on the 6-hourly Brier score. The mean random − oracle gap is a small fraction of its per-seed SD. The likely causes are the same as in §3.1: 7 passes per 72 h, 5.35 executed acquisitions per pass and capacity/demand 0.27 (r1: 2.47 and 0.12), a 6 h evaluation grid against 3–24 h activity dynamics, and many active sources below the VS-A Q50. This is a scenario finding. The planner has not been tuned, and neither the reference, the metric nor the SD rule has changed. The remedy is decision H3 (§6).

### 3.3 SCI-10 calibration on the pinned m0 scenario (18 Oct 2026)

Command: `python -m aether.evaluation.calibration --output-dir runs/gate-pinned --policies random_feasible,oracle --n-seeds 30`. It reuses the 60 pinned m0 gate records, at code identity `c79062f5…`, commit `272aba5`. Seed-cluster percentile bootstrap, 2,000 resamples (D10). Artifact: `experiments/results/sci10-pinned-m0/calibration-m0-references.json`.

| Policy | 90% flux coverage (all points) | 95% seed-cluster CI | Reliability bins whose CI excludes 0 | Calibration-in-the-large (z − p) |
|---|---:|---|---|---|
| random_feasible (selection independent of truth) | **0.910** | [0.896, 0.924] | none | −0.001 [−0.025, 0.022] |
| oracle reference (selection reads truth) | 0.917 | [0.902, 0.932] | bins 0 and 6 | −0.013 [−0.037, 0.009] |
| adaptive_eig (first 5 tuning seeds; selection depends on beliefs only) | 0.911 | [0.873, 0.949] | **bins 0 and 9** | −0.008 [−0.051, 0.040] |

adaptive_eig: `python -m aether.evaluation.calibration --output-dir runs/sci10-adaptive --policies adaptive_eig --n-seeds 5 --workers 5`. Commit `28fbff9`, clean tree, code `83d8e122…`, 860 s. Artifact: `experiments/results/sci10-pinned-m0/calibration-m0-adaptive_eig-5seeds.json`.

**adaptive_eig does not meet the reliability rule as written.** The rule says every populated bin's 95% seed-cluster CI must contain 0. Bins 0 and 9 each hold only 9 points from 3–4 seeds: observed 0/9 at mean forecast 0.082, and 9/9 at 0.939. With all-0 or all-1 outcomes, the seed-cluster bootstrap collapses to a single residual that excludes 0 by construction. A plain binomial check is consistent with calibration (P(0/9 | 0.082) = 0.46; P(9/9 | 0.939) = 0.57), but changing the rule now (for example adding a minimum bin count or a binomial test) would be a method change made after seeing results. It is recorded as decision **H6** and has not been applied. Coverage meets the band.

**Verdict.** The registered SCI-10 criteria (coverage in [0.85, 0.95]; reliability within sampling error) are met on 30 seeds for random_feasible, the reference whose observation choice does not depend on truth. The oracle's two off bins are expected: it chooses what to observe from z_true, so its evidence is not ignorable, and it is not a calibration test of the belief model.

**Caveat (strength of evidence).** 5,977 of 7,200 evaluation points lie in the 0.2–0.3 bin, around the stationary prior of 0.291. Coverage is likewise dominated by sources whose interval is still close to the prior, and truth is drawn from that prior. The criteria therefore test posterior calibration *after observation* only weakly: the bins away from the prior hold 36–674 points, with wide CIs. The compact gate records do not mark which sources were observed, so observed-only coverage is not reported. adaptive_eig calibration (the Work_Plan's default pair) is listed under "not run" in §6.

### 3.4 h168_long_horizon diagnostic for decision H3 (7 tuning seeds, 18 Oct 2026). **Does not separate**

Claude-2's proposed check before adopting H3 option A: the G4.5 rule, run unchanged on `h168_long_horizon` (168 h, 60 sources: 20 plume-seeded, 40 uniform fill per seed) for the first ten tuning seeds. Reference policies only. Same oracle reference, same metric, same SD rule. This is a **subset diagnostic, not the registered 30-seed verdict** (`seed_subset_only: true`). Records: Windows 11 / Python 3.13.9, merged with `scripts/merge_gate_records.py`, which derives the verdict through `run_gate` with a run function that refuses to compute.

| Quantity | Value |
|---|---|
| Seeds | 1000, 1002, 1003, 1004, 1005, 1006, 1009 |
| Mean random − oracle Brier gap | -0.0006 |
| Paired SD | 0.0068 (SE 0.0026) |
| Required (2 × SD) | 0.0136 |
| Seeds where the oracle beat random | 3 / 7 |
| Passes per 72 h (random_feasible) | 6.86 (16 per 168 h on every seed) |
| Executed acquisitions per pass | 6.69 to 7.06 |
| Capacity / demand | 0.115 |
| Reference checker violations | 0 |

**Interpretation.** The longer horizon fixes capacity: every seed has at least 6.6 executed acquisitions per pass, against the G1-F minimum of 4, and 6.9 passes per 72 h. It does not fix discriminability. The mean gap is indistinguishable from zero, and passing would need a true mean gap about 2 SD above zero. With the observed mean and SE, that is several standard errors away, so more seeds are very unlikely to change the conclusion. That is a judgment, not a registered test. Capacity / demand is lower than on the 72 h base (0.27), because the source count tripled while passes grew 2.3×. The likely limits are the same as in §3.2: the 6 h Brier grid against 3–24 h activity dynamics, and many sources below the sensor's Q50.

**Consequence for H3.** Option A alone is not supported by this evidence. Remaining options: A+B (h168 plus a denser fleet, so capacity / demand rises), a registered change to the evaluation question (option C, not recommended after seeing results), or D (keep the scenario and report a likely null). Nothing registered has changed. Artifacts: `experiments/results/g45-h168-diagnostic/`.

**Desktop run.** A parallel run of seeds 1010–1029 on a second machine (Linux, 31 GiB) was killed by the operating system's out-of-memory handler within 14 minutes. Each h168 geometry computation peaks at about 6.5 GB, and 20 workers were started. It produced no records. Its log is kept in the results repository and is not used here.

## 4. Known caveats that apply to any future result

- **EMIT flux comparison (SCI-08) is uninformative about the population prior.** The 73
  quantified Permian EMIT V002 rates (median 1,701 kg/h vs prior median 308) are detection- and
  quantification-selected. `NA` rates coincide exactly with missing wind. The provider's rate
  uncertainty has no public statistical definition and stays `UNKNOWN`. Details:
  `model-card-source-state.md`, `experiments/results/sci08_emit_flux.json`.
- **Persistence is uncalibrated to Cusworth's 26% statistic.** The user decided to retain current
  m0 assumptions and benchmark scope, with the regime values explicitly treated as unverified.
  Cusworth's statistic is detected-plume counts per overflight for selected sources with at least
  three overflights; it is not an unconditional active fraction. See the updated SCI-08 discussion
  in `model-card-source-state.md`. Report regime-stratified results and the registered m1 sensitivity
  family without claiming the current parameters are calibrated to that study.
- **Flux prior forms now agree by construction:** truth uses an inverse-CDF draw from the truncated
  lognormal and the belief integrates that same truncated distribution. The previous clipping / 1.8%
  endpoint-mass caveat is stale. The 5,000-source KS test is included in the recorded 294-test
  backend suite.
- The success criterion compares against `largest_first`. The `greedy_eig` comparison is reported
  with equal prominence and isn't optional.

## 5. Completed offline demo acceptance

- The recorded backend suite passed **294 tests** (`runs/demo/rehearsal/backend-tests.log`). The
  production frontend build succeeded, and the final browser suite passed **13 tests**, including
  actual artifact/API replay (`runs/demo/rehearsal/browser-tests.log`). The documented fresh backend
  installation passed all 14 API tests (`docs/demo-console.md`).
- The two demo RunRecords have one validation record per plan and zero checker violations. Acceptance
  records byte-identical replay and verified export reloads (`runs/demo/acceptance.json`).
- The actual base-config development batch has six RunRecords and zero checker violations. This is
  execution and display evidence for one family and two development seeds, not a research verdict.

### 5.1 Pinned-data demo and development comparison (18 Oct 2026)

`scripts/demo.sh` on the integrated build (`runs/demo-pinned/`, regenerated on the final revision in `runs/demo-final/`). Both demo records (`configs/demo.yaml`, seed 1000) have one independent validation per plan and zero violations: `largest_first` has 41 plans and 37 acquisitions; `adaptive_eig` has 47 plans and 51 acquisitions. Replay in a separate process is byte-identical, and both exports reload with all 46 input hashes re-verified. The scripted hour-20 forecast logs a revision but changes no selection; `docs/demo-console.md` step 5 gives the reason.

The development comparison (base config, m0, development seeds 1000 and 1001, 3 policies, 0 checker violations) is **two seeds**. Paired differences are listed only to show the pipeline works. Adaptive − largest-first Brier: −0.0145. Adaptive − greedy: −0.0032. Recall@5: +0.1 and −0.4. **Bootstrap intervals from n = 2 carry no inferential weight.** No claim about adaptive_eig follows from them. G4.5 (§3.2) shows that this scenario cannot separate even an oracle-informed reference from random.

## 6. Scientific gates and pending decisions (18 Oct 2026)

| Gate / scope | Status | Evidence and what remains |
|---|---|---|
| G1-F capacity | **FAIL** | 7 passes; per-pass optimum 9, 10, 9, 6, 10, 8, **2**; Codex-3 witness confirms 2 (`experiments/results/g1f-pinned-base/`) |
| G3 inference | Unit-level **PASS**. SCI-10: random_feasible (30 seeds) **meets** the registered criteria (weak-test caveat); adaptive_eig (5 seeds) meets coverage but **fails** the reliability rule as written: two 9-point extreme bins, degenerate bootstrap | §3.3; rule interpretation is H6 |
| G4.5 discriminability | **FAIL** (synthetic m0 pilot and pinned data) | §3.1, §3.2 |
| Power / seed count | **Not run** | Needs the 900-run development matrix. Measured costs (adaptive_eig about 12.6 min per 72 h run; reference runs about 2 min with warm geometry) put it at roughly 4 h of wall time on 9 workers. It is pointless before a scenario decision |
| Protocol lock and freeze | **Not done**; mechanism implemented | `aether.evaluation.freeze` and holdout guard tests. Nothing is locked or tagged |
| G5 science (holdout) | **Not run** | Refused by the lock guard until the steps above are done |

**Decisions pending human review.** These were not taken during integration; nothing registered has changed.

| # | Decision | Options (evidence) | Integrator recommendation |
|---|---|---|---|
| H1 | G1-F contingency (Register: "switch the demo to `h168_long_horizon`") | (a) keep the 72 h pinned demo with G1-F shown as failed; (b) add a labelled h168 demo; (c) make h168 the primary demo. h168 has 168 h and 60 sources (20 plume-seeded, 40 fill). **Diagnostic G1-F on h168 (fill seed 1000) meets both thresholds:** 16 passes (6.9 per 72 h); every pass has at least 5 checker-valid acquisitions (8 proven OPTIMAL, 8 time-limited lower bounds); `experiments/results/g1f-h168-diagnostic/`. Windows took 56 min; planning estimate 1.5–2.5 h of compute per demo seed | (a) for this submission. The submitted demo stays on base, labelled. Then (b). The h168 capacity evidence above supports it; check more fill seeds first |
| H2 | D9 family scope sign-off | all six families (proposed) / m0 only / m0 + 2 of m1–m4. Every option includes m0, which fails, so today's verdict is FAIL under each | All six (D9 as proposed) |
| H3 | G4.5 scenario remedy | A: h168 base; A+B: h168 + denser fleet; C: evaluation-time metric change (not recommended); D: keep the scenario and accept a likely null. **h168 diagnostic (§3.4): capacity fixed, discriminability not** (gap ≈ 0 vs 2 SD ≈ 0.014) | A alone is no longer supported. Choose between A+B (needs a registered fleet change and a new gate run) and D (report the null). Integrator: D for this submission, A+B as the next study |
| H4 | SD-not-SE rule, and the oracle as an oracle-informed greedy reference | Kept as registered (§3 notes 1–2) | Keep |
| H6 | SCI-10 reliability rule for tiny bins | Keep as written (adaptive_eig fails), or pre-register a minimum bin size or a binomial check for bins whose seed-cluster bootstrap is degenerate, then re-evaluate | **Decided by the user (18 Oct 2026): keep as written.** adaptive_eig is reported as failing the reliability rule; the binomial-consistency note stays as context, not as a pass |
| H5 | G5/G6 sign-off | Concrete artifacts in `docs/p0-requirements-evidence.md` | Pending the user's review |

The old two-seed demo comparison is preliminary and synthetic-placement only. The pinned-scenario development comparison in §5.1 is also preliminary (two seeds, m0). Neither is a research claim.

## 7. Cross-platform reproducibility (REL-05, 18 Oct 2026)

Base m0, seed 1000, oracle and random_feasible references, re-run on Windows 11 / Python 3.13.9 (Intel Core Ultra 7 258V) and compared with the committed `g45-pinned-dev` values (Linux / Python 3.14.7). Package versions are identical (astropy 8.0.2, numpy 2.5.4, ortools 9.15.6755, scipy 1.18.1, sgp4 2.27, skyfield 1.55).

| Value | Committed (Linux) | Windows | Difference |
|---|---|---|---|
| oracle Brier | 0.22919438427351319 | 0.2291943842735133 | ≈ 1e-17 |
| random_feasible Brier | 0.23797797908569931 | 0.23797797908569926 | ≈ 5e-17 |
| passes, random_feasible acquisitions | 7, 36 | 7, 36 | exact |

Selections and counts reproduce exactly. Brier scores differ only in the last floating-point digit. Byte-identical replay is therefore a **within-platform** property: same OS, Python build and packages. It is not byte-identical across platforms. Records merged across machines for one gate must come from the same platform, and `scripts/merge_gate_records.py` stops on any byte difference between two copies of a record. The h168 gate records are produced on two Windows / Python 3.13 machines for this reason.

**BLAS thread count (same machine, 18 Oct 2026).** The h168 demo, largest_first, seed 1000, was replayed on the same Windows machine twice. With `OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=1`, matching the original run, the record is byte-identical (SHA-256 `1a2bbdd2…57fcf` both times). With the default multi-threaded BLAS, it is not (`6d8d2652…df62b`). Every plan selection and acquisition outcome was identical; scene cloud fractions, utilities and beliefs differed only in the last floating-point digit (max |Δ p_active| = 3.3e-16). Byte-identical replay therefore also requires a fixed BLAS thread count. `scripts/demo.sh` now pins it. Follow-up for the integrator, once the h168 records are merged: set the thread count inside the runner and record it in the run's environment. Doing it now would change `code_sha256`, which every run-matrix record carries.

