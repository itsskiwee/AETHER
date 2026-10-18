# Completion batch — Claude-2 (science models, evaluation, research integrity)

Session: aether-5b. Branch `lane/C2-science-eval`, worktree `../AETHER-c2`. Started 18 Oct 2026.
Owns: `backend/aether/sensors/`, `backend/aether/belief/`, `backend/aether/evaluation/`,
`experiments/` (protocol lock goes through Claude-1), `docs/model-card-*.md`,
`docs/validation-report.md`, `docs/experiment-protocol.md`.

## Done (Wave A)

- **G4.5 driver** `aether.evaluation.gate` on a new parallel, resumable run matrix
  `aether.evaluation.matrix`. The benchmark uses the same matrix (`benchmark(..., workers=N)`). It
  refuses holdout seeds and binds protocol/seed/config hashes, `RunRecord.input_dataset` and the git
  commit. Family scope is decision D9 in the validation report (all six families must pass).
- **SCI-10 analysis** `aether.evaluation.calibration`: seed-cluster bootstrap reliability and 90%
  flux coverage (D10). The CLI reuses the gate's record store.
- **SCI-08 EMIT comparison** `experiments/sci08_emit_flux.py` →
  `experiments/results/sci08_emit_flux.json`; written up in `docs/model-card-source-state.md`.
  The result is descriptive only: the selected sample can't validate PR-P10.
- Tests: `tests/unit/test_evaluation_gate_calibration.py`.

## For other roles

- **Codex-1 (ingestion):** keep `uncertainty_kind = UNKNOWN` for
  `Emissions Rate Estimate Uncertainty (kg/hr)`. The public ATBD v0.2 and User Guide v02
  (April 2025) do not define it (model card SCI-08 item 4). Observed: `NA` rate ⇔ `NA` wind in all
  155 Permian records. `missing_rate_reason` can say "provider did not quantify (no wind; ATBD
  §4.2.5 screening)" but should not claim a cause beyond that.
- **Claude-1 (register owner):** proposed text for PR-P10's [V] cell: "SCI-08 (18 Oct 2026): 73
  quantified EMIT V002 Permian rates, median 1,701 kg/h vs prior 308; detection- and
  quantification-selected, so uninformative about the population prior. Kept [A]; upper tail
  (σ_ln) and the EMIT uncertainty definition are added to the §10 domain-review list."

## Next

1. Pilot G4.5 on the synthetic-only scenario (early warning; labelled and superseded).
2. After DATA-02 merges: G4.5 on the wired scenario, then SCI-10 on m0 (5 seeds adaptive_eig +
   random_feasible), then the 900-run development matrix for paired SDs → power calculation.
3. Lock (Claude-1 commits and tags) → holdout → all-family results.
