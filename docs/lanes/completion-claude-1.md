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

- PERF-01 (`lane/PERF-01-timing-artifact`): new contracts `RunPerformance`/`PlanTiming`; `runner.run_policy_with_performance` returns `(RunRecord, RunPerformance)` with the RunRecord identical to `run_policy`'s; `Plan.runtime_s` stays None. CLI `simulate` writes `performance.json`; `export` packs it with `performance_json_sha256` and refuses a run-id mismatch. New `tests/integration/test_closed_loop.py` (12 h, 6 sources) is the first automated end-to-end check of INT-04 byte determinism across a fresh window computation.
- PERF-02 (`lane/PERF-02-window-cache`): window cache keyed on exactly what `generate_windows` reads (spacecraft, sensors, window_search, sources, interval, ephemeris/EOP bytes, orbit code hash), so families and policies share geometry. Optional disk cache via `AETHER_WINDOW_CACHE_DIR` (atomic writes, contract revalidation on load). `RunPerformance.windows_source` is one of computed, process_cache or disk_cache. A test checks records are byte-identical with the cache disabled, empty and full. Measured first: a 12 h / 6-source window build took 28.8 s, and the pilot showed ~450 s per (family, seed) for 72 h.
- Merged Claude-2: C2-01 (gate driver, matrix, SCI-10, SCI-08), C2-02 (code SHA-256 in record identity), C2-03 (ephemeris/EOP bytes and package versions in identity), C2-04 (oracle passed no `now_utc`, capping it at one look per source per run).
- Register: PR-P10 [V] text from SCI-08; §10 review list adds σ_ln and the EMIT uncertainty definition.

## Requests to other roles
- **Codex-3:** `tests/unit/test_checker.py:456` calls `greedy_insert` without `now_utc`. Claude-1 plans to make `now_utc` required, because the `None` default silently counts the whole history against the per-solve source cap, which is the C2-04 bug class. Please pass `now_utc` there, then tell Claude-1.
- **Codex-1:** if bulk raw files leave the git index, keep the 10–20 selected metadata/TIFF pairs listed in `emit_permian.json` tracked (or another checked-in permitted copy). FR-DATA-008 requires a demo usable from checked-in sample data, and the runner refuses to start when a manifest-listed file is missing.
- **Codex-1:** keep `uncertainty_kind = UNKNOWN` for `Emissions Rate Estimate Uncertainty (kg/hr)`; the provider documents do not define it (Claude-2, SCI-08). In all 155 Permian records an `NA` rate occurs exactly when wind is `NA`. The missing reason may say the provider did not quantify the rate, without claiming a further cause.

## Waiting on
- Codex-1: `load_pinned_plume_dataset`, `data/manifests/emit_permian.json`, `data/normalized/emit_permian_plumes.json` (DATA-01).
- Claude-2: review of the interface and of the rule that historical rates never set truth or the prior.

## Notes for the user
- `data/raw/EMITL2BCH4PLM_002-20261018_042728/` (about 113 MiB, 3,372 files) is committed to git in `a70976e`. The completion prompt says to keep bulk raw files out of git. Removing them from history is your decision; nothing has been changed.
