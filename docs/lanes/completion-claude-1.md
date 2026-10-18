# Completion batch: Claude-1 status (integration, contracts, execution and release)

Session `aether-be`. Worktree `../AETHER-wt/claude-1`. Ownership: `Implementation/Work_Plan.md`, "Completion batch".

## Done
- Recorded the six-agent ownership map in Work_Plan as a superseding assignment (18 Oct).
- Proposed the pinned plume dataset interface: `docs/dataset-interface.md`.

- DATA-02 (runner side) on `lane/DATA-02-dataset-wiring`:
  - `SourcesConfig.plume_dataset` (PR-P04) is part of `config_hash`. Manifest paths must be repo-relative, the hash is required, and the dataset must match between the model and truth views. `load_scenario(..., synthetic_only=True)` clears it.
  - New contract `InputDatasetRef` and `RunRecord.input_dataset`, cross-checked against the run's sources. The `DATA_READY` event carries the same ref.
  - `runner.resolve_sources` loads the configured dataset once per process through `aether.ingestion.load_pinned_plume_dataset`. Loader errors propagate; nothing falls back to uniform placement. Explicit plumes plus a configured dataset raise `ValueError`.
  - CLI `windows`/`simulate` accept `--synthetic-only`. Run manifests record `plume_dataset` and hash the dataset manifest.
  - Checks: the full backend suite passed (11.5 min, single process) except the contract round-trip coverage test, which needed an `InputDatasetRef` example. After adding it, the round-trip, wiring and contract-boundary tests pass, ruff check and format are clean, and `validate` succeeds for base and demo.
  - Every config hash changed, because the dumped config gains `sources.plume_dataset: null`. Existing uncommitted `runs/demo` artifacts carry the old hash. The demo will be regenerated after the real dataset is wired.

## Doing
- PERF-01: measured planning wall time in a separate performance artifact.

## Waiting on
- Codex-1: `load_pinned_plume_dataset`, `data/manifests/emit_permian.json`, `data/normalized/emit_permian_plumes.json` (DATA-01).
- Claude-2: review of the interface and of the rule that historical rates never set truth or the prior.

## Notes for the user
- `data/raw/EMITL2BCH4PLM_002-20261018_042728/` (about 113 MiB, 3,372 files) is committed to git in `a70976e`. The completion prompt says to keep bulk raw files out of git. Removing them from history is your decision; nothing has been changed.
