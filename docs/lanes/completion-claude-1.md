# Completion batch: Claude-1 status (integration, contracts, execution and release)

Session `aether-be`. Worktree `../AETHER-wt/claude-1`. Ownership: `Implementation/Work_Plan.md`, "Completion batch".

## Done
- Recorded the six-agent ownership map in Work_Plan as a superseding assignment (18 Oct).
- Proposed the pinned plume dataset interface: `docs/dataset-interface.md`.

## Doing
- DATA-02: config `sources.plume_dataset`, `RunRecord.input_dataset`, runner loading and verification, CLI `--synthetic-only`, export hashes.

## Waiting on
- Codex-1: `load_pinned_plume_dataset`, `data/manifests/emit_permian.json`, `data/normalized/emit_permian_plumes.json` (DATA-01).
- Claude-2: review of the interface and of the rule that historical rates never set truth or the prior.

## Notes for the user
- `data/raw/EMITL2BCH4PLM_002-20261018_042728/` (about 113 MiB, 3,372 files) is committed to git in `a70976e`. The completion prompt says to keep bulk raw files out of git. Removing them from history is your decision; nothing has been changed.
