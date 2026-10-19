# Product connection and replay delivery — 18 October 2026

The earlier audit is superseded for integration/data status: Claude has integrated the lane changes, made retrieval time nullable, generated the pinned dataset, configured the base scenario and produced a new pinned-data demo. These changes were already present when this follow-up began; they were preserved rather than reimplemented.

## Running product

- Console: http://127.0.0.1:4311
- API documentation: http://127.0.0.1:8011/api/docs
- Serving source: `/home/itsskiweee/Projects/AETHER-wt/int-b`
- Actual artifacts: `/home/itsskiweee/Projects/AETHER-wt/claude-1/runs/demo-pinned`

The existing Claude-owned server/jobs were left running. Both the console HTML and production API responded successfully. Direct API reads of both records, their historical context and manifests confirmed:

| Policy | EMIT-seeded sources | Uniform fill | Windows | Plans / validations | Acquisitions |
|---|---:|---:|---:|---:|---:|
| adaptive_eig | 20 | 0 | 1,494 | 47 / 47 | 51 |
| largest_first | 20 | 0 | 1,494 | 41 / 41 | 37 |

Both historical-context responses say pinned; both input manifests enumerate 46 input files. The existing acceptance records report byte-identical replay, verified exports and zero checker violations. This follow-up directly checked that every bundled validation is successful with no violations. Browser automation was unavailable (no enabled browsers), so this follow-up does not claim a new visual/accessibility rehearsal.

## Portable delivery

`/home/itsskiweee/Projects/AETHER-deliverables/AETHER-pinned-replay.zip`

- Source snapshot: committed revision `ed1f7fd096aa514f6fdb030e34dafd9eca4ce9ce` from int-b. Concurrent uncommitted edits are excluded.
- Size: 19,720,832 bytes (about 18.8 MiB).
- SHA-256: `746583155c554f1e1e0a930f0e5caeea754ac600b157fc2f68fa3c1034c00c43`.
- Contents: 256 files, including START_HERE.md, per-file hash index, source/configs/pinned inputs, both demo records, performance artifacts, exports and acceptance record. Dependencies are not bundled; setup requires initial package installation.
- Unfinished comparison jobs, caches and later scientific results are excluded. The comparison screen may show unavailable in this fixed replay package.

The builder is `scripts/package_replay.py` in AETHER-codex1. It verifies record acceptance hashes, pinned sample hashes and schedule validation before packaging. The archive was extracted into a separate temporary folder; all 255 indexed file hashes/sizes matched. Using the extracted source, both bundled exports passed `python -m aether.cli verify-export`, each verifying 46 inputs / 42 dataset files. This establishes extraction/export portability; it is not a full fresh-install or combined release-suite result.

## Remaining acceptance

G1-F capacity still fails on one pinned-scenario pass. The synthetic G4.5 pilot failed; pinned gate and development work are running in the Claude worktree. No holdout or adaptive superiority is claimed. The hour-20 forecast event changes no selected option in the pinned demo. The submission guide states these limits explicitly. Scientific decisions and final combined release acceptance remain separate from this working replay delivery.
