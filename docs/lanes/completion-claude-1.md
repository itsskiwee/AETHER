# Completion batch: Claude-1 status (integration handoff, 18 Oct 2026)

Session `aether-be`. Assignment: `docs/claude-completion-fix-prompt.md` (cross-lane integration, six-hour deadline). The deadline is recorded as 14:49 EDT / 18:49 UTC, six hours after the session started at 08:49 EDT. Branch `lane/INT-09-completion-integration`, based on `main` 302d0b0. Work done while the pinned gate was running was committed on `lane/INT-09-wip` in `AETHER-wt/int-b` and then fast-forwarded in, so the gate's recorded commit and code identity stay accurate.

**Implementation is integrated. Scientific acceptance is not complete.** G1-F failed and G4.5 failed. Calibration is reported in the validation report. The power calculation, the protocol lock and the holdout are pending a human scenario decision.

## Integrated (one scoped commit per lane, authorship named)

| Commit | What |
|---|---|
| `e85313d` | Merge of C2-06: synthetic-only m0 G4.5 pilot, FAIL (gap 0.00476, SD 0.02205, threshold 0.04411, 15/30 seeds) |
| `2ecbbce` | Contract: `DataSource.retrieved_at_utc: UtcDatetime \| None`, required and explicit; still strictly UTC when known |
| `4ed2109` | Codex-1 V002 parser aliases, inventory, pinned loader and preparer, from the uncommitted `AETHER-codex1` diff. Its staged bulk removals were not replayed |
| `b9d7ee9` | Pinned sample tracked. The bulk download left the index (`git rm --cached`; local files untouched; history not rewritten) |
| `643d8c5` | `configs/base.yaml` pins the manifest by SHA-256 |
| `72e0486`, `7d8a1d6` | Codex-2 capacity builder, tests and candidates; Codex-3 checker hardening and witness. The checker still imports no solver or policy code |
| `6de5b33` | `now_utc` is required in `greedy_insert`, `can_add` and `rejection_reasons`. Every production caller already passed it. Tests now pass it, and a new regression test checks that a completed commitment releases the source cap but keeps its slot |
| `033ee98` | Run/export lineage v1, `verify-export`, and `--synthetic-only` on benchmark and gate (it reaches every run) |
| `6cb1ac3` | Integrated G1-F evidence (FAIL) |
| `6396bec` | Codex-4 console/API patch. API tests now use the real contract instead of `model_dump` doubles |
| `df27883` | Scientific freeze identity (`experiments/freeze.json`) enforced at holdout entry |

## Dataset (DATA-01)

- Inventory reproduced byte for byte: `c7f591ad…ff74`. 1,686 JSON/TIFF pairs, all accepted; 155 regional records (73 numeric, 82 `NA`); 144 regional 500 m clusters. No discrepancy with the reported counts.
- Sample: 20 records (10 quantified, 10 `NA`), 20 distinct clusters, all inside the bbox, no duplicates. Manifest `216cf916…982c55`; normalized `ba4305b3…94343` (20 records, 127,928 bytes); 40 raw files. Retrieval `PARTIAL`, time null.
- Fresh clone (29 MB working tree, without the bulk directory): sample and wiring tests pass, `validate` reproduces config hash `91920c15…f5c079`, and source resolution verifies the dataset and seeds 20 sources.

## Gates and science (all evidence on the pinned scenario unless labelled)

| Item | Verdict | Evidence |
|---|---|---|
| G1-F | **FAIL**: 7 passes ✓; per-pass optimum 9, 10, 9, 6, 10, 8, **2** ✗. Codex-3 witness lower bounds 7, 7, 7, 5, 8, 6, 2. Windows byte-identical to Codex-2's historical candidate | `experiments/results/g1f-pinned-base/` |
| G4.5, synthetic m0 pilot (C2-06) | **FAIL**: gap 0.00476 vs 2 SD 0.04411; 15/30 seeds | `experiments/results/g45-pilot-synthetic-m0/` |
| G4.5, pinned, 6 families × 30 seeds | **FAIL in all six**: gaps −0.0004 to 0.0026 vs 2 SD 0.0179–0.0259; 0 checker violations in 360 runs | `experiments/results/g45-pinned-dev/` |
| SCI-10, m0 | random_feasible (30 seeds) meets the criteria (weak test: 83% of points near the prior). adaptive_eig (5 seeds) meets coverage 0.911 but **fails** the reliability rule as written: bins 0 and 9 have n = 9 and a degenerate bootstrap; binomial checks give 0.46 and 0.57. Decision H6 | `experiments/results/sci10-pinned-m0/` |
| Power calculation | **Not run**: needs the 900-run development matrix; blocked by decision H3 | — |
| Lock / freeze | Mechanism implemented and tested; **nothing locked or tagged** | `backend/aether/evaluation/freeze.py` |
| Holdout (G5) | **Not run** (refused by the guard) | — |

Pending human decisions H1–H6 (G1-F demo contingency, D9 sign-off, G4.5 remedy, SD/oracle wording, G5/G6 sign-off, SCI-10 tiny-bin rule) are written out with options and recommendations in `docs/validation-report.md` §6. When asked mid-run, the user chose to continue without deciding, so every registered value is unchanged.

## Demo (pinned data)

`runs/demo-final/` was regenerated on the final code and matches the earlier `runs/demo-pinned/` byte for byte for `largest_first`. `largest_first`: 41 plans, 37 acquisitions; `adaptive_eig`: 47 plans, 51 acquisitions; 0 violations. Separate-process replay is byte-identical, and both exports reload with 46 input hashes re-verified. The hour-20 forecast revision changes no selection; `docs/demo-console.md` step 5 explains why. The two-seed development comparison carries no inferential weight. PRD 22.1 screenshots: `runs/demo-pinned/rehearsal/*.png`.

## Measured cost (reference machine: 12 CPUs, Python 3.14.7)

- Cold 72 h geometry for 20 sources: 385.5 s with the machine partly loaded, 699.3 s fully loaded. Warm (disk cache): about 0.1 s. Timings depend on load.
- Pinned reference runs (oracle or random_feasible), 9 parallel workers: the 360-run gate took 72 min; per run 17.4–796.9 s, median 88.0 s (the maximum includes r1's cold geometry).
- adaptive_eig, demo seed 1000: 757 s per run, of which 612 s is CP-SAT across 47 plan calls (max 108.7 s); largest_first takes about 50 s plus geometry.
- Planning estimate (not measured): the 900-run development matrix needs roughly 4 h of wall time on 9 workers, dominated by 180 adaptive_eig runs and the greedy_eig runs. Holdout at N = 100 is 3,000 runs, roughly 13 h.

## Notes

- A peer session ran `aether.evaluation.gate --output-dir runs/g45-smoke` in the original `AETHER` checkout during this work. It is not part of this integration, and that checkout's `runs/demo` was not touched by Claude-1.
- Bulk raw files: switching an older checkout (for example `AETHER` at `ee87199`) to this branch makes git remove the now-untracked bulk files from that working tree. They stay recoverable from commit `a70976e`. Copy them aside first if that checkout is ever switched.
