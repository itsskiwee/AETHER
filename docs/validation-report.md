# AETHER — Validation Report (L3)

## Current status — offline demo delivery (17 Oct 2026)

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
| `solver_runtime_p95_s` | 95th percentile of `Plan.runtime_s` | lower | no plans |
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

## 3. Discriminability gate G4.5 (EVL-08): not yet run

Rule as written in `protocol.yaml`: mean(random − oracle Brier) > 2 × **SD** of the per-seed paired
difference on the 30 tuning seeds.

Notes for the reviewer:

1. **The rule uses SD, not standard error.** It asks that the oracle beat random on almost every
   seed, which is much stricter than "the mean gap is significant". I implemented it as written.
   If the intent was SE, change it before locking.
2. **The oracle is a greedy reference, not a proven bound.** `OraclePolicy` knows z_true at each
   option time and ranks windows by p_valid × (p_now − z_true)², but it plans myopically through
   the same greedy insertion as the baselines. A smarter policy could in principle beat it. Report
   it as "oracle-informed greedy reference".
3. Capacity/demand is reported per tuning seed as acquisitions / (sources × passes). A ratio near
   1 means the policies can differ only in ordering.
4. **Seed-count procedure:** `seed_count_rule` uses the approved **minimum effect** (absolute paired
   Brier difference). The user approved **0.01 Brier points** for 80% power on 17 Oct 2026; this is
   now recorded in the still-unlocked protocol. `stats.seeds_for_power(sd, min_effect)` can compute
   the required count after valid tuning-seed paired SD is available.

## 4. Known caveats that apply to any future result

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

## 6. Scientific gates

| Gate / scope | Current status | Evidence and remaining work |
|---|---|---|
| G3 — Inference | **Not established as a scientific result** | The development artifacts contain evaluator scores, but they cover only two seeds in m0. SCI-10 calibration and model-assumption review remain unfinished. |
| G4.5 — Discriminability | **Not run** | The comparison batch has no oracle/random results; the gate quantities and tuning-seed paired variation are not established by this batch. |
| G5 — Science | **Unfinished** | Only the m0 family and two development seeds are present. The protocol is unlocked and no holdout validation was run. |

The offline demo acceptance (G6 scope) is complete for the documented demonstration: actual records,
replay/export checks, production API/browser replay, 294 backend tests, and 13 browser tests are
recorded above and in `docs/demo-console.md`. The hour-20 forecast event is logged, and the adaptive
record changes selected option IDs, demonstrating feedback behavior in the simulated run.

The two-seed comparisons remain preliminary and insufficient for research claims. `experiments/protocol.yaml`
is still unlocked, and no holdout validation is represented here. The retained m0 persistence
assumptions remain unverified. The approved 0.01 Brier-point minimum effect is recorded in the
protocol, while valid tuning-seed variance for the seed-count procedure remains to be established.
