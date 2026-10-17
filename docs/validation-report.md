# AETHER — Validation Report (L3)

**Status, 17 Oct 2026: no benchmark has run.** The runner (INT-03) doesn't exist yet. Every number
in this file is a definition, a decision or a test fixture. None of it is an experimental result.
Results sections are added only from `benchmark-confidence-intervals.json` files, with their
protocol hash and lock tag.

Owner: L3 (Evaluation & integrity). Code: `backend/aether/evaluation/`.

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
4. **Open input needed:** `seed_count_rule` needs a pre-stated **minimum effect** (Brier
   difference). The protocol doesn't state one. `stats.seeds_for_power(sd, min_effect)` is ready;
   someone must choose `min_effect` before locking.

## 4. Known caveats that apply to any future result

- **Persistence may be overstated about 2× vs the Permian** (L2, `model-card-source-state.md`
  SCI-08). Adaptive revisits may look better here than on real Permian intermittency. Report
  per-regime results and m1 with this caveat. The regime decision rests with L1 and the user.
- **Truth flux prior clips at [30, 30 000] kg/h while the belief truncates** (PR-B06, needs L6).
  About 1.8% of sources sit at exactly 30 kg/h, so m0 flux coverage near the floor may be slightly
  off until this is fixed.
- The success criterion compares against `largest_first`. The `greedy_eig` comparison is reported
  with equal prominence and isn't optional.

## 5. Results

None yet. The first entry will be the G4.5 verdict on tuning seeds.
