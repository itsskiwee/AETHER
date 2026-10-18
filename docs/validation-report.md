# AETHER — Validation Report (L3)

## Current status — integrated pinned-data build (18 Oct 2026)

The base scenario now places its 20 source hypotheses at 20 pinned historical EMIT V002 Permian plume locations, with 0 uniform fill (`configs/base.yaml`, PR-P04). Every result below uses that scenario unless it is labelled synthetic-only. **Implementation is integrated; scientific acceptance is not complete.**

| Item | Result | Section |
|---|---|---|
| G1-F capacity, integrated scenario | **FAIL**: 7 passes ✓; one pass with at most 2 acquisitions ✗ (minimum 4) | §6, `docs/orbit-model-report.md` |
| G4.5, synthetic-only m0 pilot (C2-06) | **FAIL** (gap 0.0048 vs 2 SD 0.0441) | §3.1 |
| G4.5, pinned data, six families, 30 tuning seeds | **FAIL** (m0 gap 0.0025 vs 2 SD 0.0256; the per-family table is in §3.2) | §3.2 |
| SCI-10 calibration, m0 pinned, 30 seeds | **Meets the registered criteria** for the truth-independent reference (random_feasible); weak evidence beyond the prior (see caveat) | §3.3 |
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

## 3. Discriminability gate G4.5 (EVL-08): pilot FAILS on m0; scenario decision pending

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

### 3.3 SCI-10 calibration on the pinned m0 scenario (18 Oct 2026)

Command: `python -m aether.evaluation.calibration --output-dir runs/gate-pinned --policies random_feasible,oracle --n-seeds 30`. It reuses the 60 pinned m0 gate records, at code identity `c79062f5…`, commit `272aba5`. Seed-cluster percentile bootstrap, 2,000 resamples (D10). Artifact: `experiments/results/sci10-pinned-m0/calibration-m0-references.json`.

| Policy | 90% flux coverage (all points) | 95% seed-cluster CI | Reliability bins whose CI excludes 0 | Calibration-in-the-large (z − p) |
|---|---:|---|---|---|
| random_feasible (selection independent of truth) | **0.910** | [0.896, 0.924] | none | −0.001 [−0.025, 0.022] |
| oracle reference (selection reads truth) | 0.917 | [0.902, 0.932] | bins 0 and 6 | −0.013 [−0.037, 0.009] |

**Verdict.** The registered SCI-10 criteria (coverage in [0.85, 0.95]; reliability within sampling error) are met on 30 seeds for random_feasible, the reference whose observation choice does not depend on truth. The oracle's two off bins are expected: it chooses what to observe from z_true, so its evidence is not ignorable, and it is not a calibration test of the belief model.

**Caveat (strength of evidence).** 5,977 of 7,200 evaluation points lie in the 0.2–0.3 bin, around the stationary prior of 0.291. Coverage is likewise dominated by sources whose interval is still close to the prior, and truth is drawn from that prior. The criteria therefore test posterior calibration *after observation* only weakly: the bins away from the prior hold 36–674 points, with wide CIs. The compact gate records do not mark which sources were observed, so observed-only coverage is not reported. adaptive_eig calibration (the Work_Plan's default pair) is listed under "not run" in §6.

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

## 6. Scientific gates and pending decisions (18 Oct 2026)

| Gate / scope | Status | Evidence and what remains |
|---|---|---|
| G1-F capacity | **FAIL** | 7 passes; per-pass optimum 9, 10, 9, 6, 10, 8, **2**; Codex-3 witness confirms 2 (`experiments/results/g1f-pinned-base/`) |
| G3 inference | Unit-level **PASS**; SCI-10 **meets the registered criteria** (random_feasible, 30 seeds) with the §3.3 caveat | adaptive_eig calibration not run |
| G4.5 discriminability | **FAIL** (synthetic m0 pilot and pinned data) | §3.1, §3.2 |
| Power / seed count | **Not run** | Needs the 900-run development matrix. Measured costs (adaptive_eig about 12.6 min per 72 h run; reference runs about 2 min with warm geometry) put it at roughly 4 h of wall time on 9 workers. It is pointless before a scenario decision |
| Protocol lock and freeze | **Not done**; mechanism implemented | `aether.evaluation.freeze` and holdout guard tests. Nothing is locked or tagged |
| G5 science (holdout) | **Not run** | Refused by the lock guard until the steps above are done |

**Decisions pending human review.** These were not taken during integration; nothing registered has changed.

| # | Decision | Options (evidence) | Integrator recommendation |
|---|---|---|---|
| H1 | G1-F contingency (Register: "switch the demo to `h168_long_horizon`") | (a) keep the 72 h pinned demo with G1-F shown as failed; (b) add a labelled h168 demo; (c) make h168 the primary demo. h168 has 168 h and 60 sources (20 plume-seeded, 40 fill). Its G1-F is unmeasured; planning estimate 1.5–2.5 h of compute per demo seed | (a) for this submission. The submitted demo stays on base, labelled. Run (b) next, re-measuring G1-F on h168 first |
| H2 | D9 family scope sign-off | all six families (proposed) / m0 only / m0 + 2 of m1–m4. Every option includes m0, which fails, so today's verdict is FAIL under each | All six (D9 as proposed) |
| H3 | G4.5 scenario remedy | A: h168 base; A+B: h168 + denser fleet; C: evaluation-time metric change (not recommended); D: keep the scenario and accept a likely null | A (Claude-2), only after H1(b) measures h168 capacity; then re-run the 360-run gate (several hours, planning estimate) |
| H4 | SD-not-SE rule, and the oracle as an oracle-informed greedy reference | Kept as registered (§3 notes 1–2) | Keep |
| H5 | G5/G6 sign-off | Concrete artifacts in `docs/p0-requirements-evidence.md` | Pending the user's review |

The old two-seed demo comparison is preliminary and synthetic-placement only. The pinned-scenario development comparison in §5.1 is also preliminary (two seeds, m0). Neither is a research claim.
