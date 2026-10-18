# Pinned plume dataset interface (DATA-01 ↔ DATA-02)

Status: **implemented and integrated, 18 Oct 2026** (`lane/INT-09-completion-integration`). Proposed by Claude-1; Codex-1 built the ingestion side; Claude-1 integrated it. Claude-2's review of the historical-rates rule is still open (§ Truth below).

| Item | Value |
|---|---|
| Manifest | `data/manifests/emit_permian.json`, SHA-256 `216cf916269f10e5a0dd0bd08b224cef2956bfa0d6990443eddf8c6a87982c55` (pinned in `configs/base.yaml`) |
| Normalized records | `data/normalized/emit_permian_plumes.json`, SHA-256 `ba4305b3876abfca607cb8a994918a945fbd168291466dc169712b5973c94343`, 20 records (10 quantified, 10 `NA` → null + `CRITERIA_NOT_MET`) |
| Raw files | 40 byte-identical copies (20 metadata JSON + 20 TIFF) under `data/raw/pinned_emit_permian_v1/`, tracked |
| Inventory | `data/manifests/emit_inventory.json`, SHA-256 `c7f591ad79fd1f33fad2d30ffc0225642730d038ccfeeac6cb28c31fad24ff74`, reproduced independently: 1,686 pairs; 155 regional (73 numeric, 82 `NA`); 144 regional 500 m clusters |
| Retrieval | `PARTIAL`: time and per-file URLs were not retained. `DataSource.retrieved_at_utc` is an explicit `null`, never reconstructed |
| Bulk download | `data/raw/EMITL2BCH4PLM_002-20261018_042728/` (3,372 files) is local and ignored. It left the index in `b9d7ee9` without being deleted; commit `a70976e` still holds it |
| Run use | base: 20 plume-seeded sources, 0 uniform fill; `h168_long_horizon`: 20 seeded + 40 fill |

The deviations from the proposal below are additive: the manifest also records `size_bytes`, `catalog_url` and selection counts; run manifests list every file (see the CLI section); `aether.cli verify-export` reloads an export and checks it again.

## Why

Historical EMIT plumes (2022–2025) are *location context* for the virtual scenario. They place some source hypotheses; they never set truth, never become simulated observations, and never show present activity. A run, a benchmark and a locked protocol must name the exact plume records they used, and every comparison must use the same records.

## Chain of identity

```
configs/base.yaml  sources.plume_dataset.manifest_sha256      (in config_hash → protocol lock)
  └─ data/manifests/emit_permian.json                         (Codex-1; hashed by the loader)
       ├─ raw_files[]: selected metadata JSON + TIFF, sha256   (only the selected records)
       └─ normalized: data/normalized/emit_permian_plumes.json, sha256
            └─ PlumeObservation records (REAL_OBSERVATION)
```

Changing any byte in the chain fails the run with a clear error. Nothing falls back to synthetic placement silently.

## Codex-1 deliverables

### 1. Manifest `data/manifests/emit_permian.json`

Minimum keys (more are welcome):

```json
{
  "schema_version": 1,
  "dataset_id": "emit-l2b-ch4plm-002-permian-v1",
  "provider": "NASA LP DAAC", "dataset": "EMITL2BCH4PLM", "version": "002",
  "citation_text": "...", "license_url": "...",
  "retrieval": {
    "status": "AUTHENTIC | PARTIAL | UNAVAILABLE",
    "retrieved_at_utc": "… or null",
    "source_urls": ["… or empty"],
    "evidence": "how the retrieval facts were established, or why they are unknown"
  },
  "selection": {
    "region_bbox_wgs84": [-104.5, 30.8, -101.0, 33.5],
    "rule": "deterministic rule text, e.g. sorted by plume id, include numeric and NA rates",
    "inventory_path": "data/manifests/emit_inventory.json", "inventory_sha256": "…"
  },
  "adapter_version": "…", "transformation_version": "…",
  "raw_files": [
    {"path": "data/raw/…/EMIT_…json", "sha256": "…", "size_bytes": 0, "role": "metadata", "native_id": "…"},
    {"path": "data/raw/…/EMIT_…tif",  "sha256": "…", "size_bytes": 0, "role": "raster",   "native_id": "…"}
  ],
  "normalized": {"path": "data/normalized/emit_permian_plumes.json", "sha256": "…", "record_count": 15},
  "known_limitations": ["…"]
}
```

Paths are relative to the repository root. Retrieval facts that cannot be established are `null`, with `status` saying so; never reconstruct them from filenames or filesystem timestamps.

### 2. Normalized file `data/normalized/emit_permian_plumes.json`

A JSON array of `PlumeObservation.model_dump(mode="json")`, sorted by `id`, canonical (`sort_keys`, UTF-8, trailing newline). 10–20 Permian records, including both numeric and `NA` rates. `NA` stays `null` with a `missing_rate_reason`. `uncertainty_kind` stays `UNKNOWN` until Claude-2 confirms the provider definition.

### 3. Loader in `aether.ingestion`

```python
class PinnedDatasetError(ValueError): ...

@dataclass(frozen=True)
class PinnedPlumeDataset:
    dataset_id: str
    manifest_path: str          # repo-relative, as given
    manifest_sha256: str        # of the manifest bytes
    normalized_sha256: str
    raw_file_count: int
    plumes: tuple[PlumeObservation, ...]   # sorted by id

def load_pinned_plume_dataset(
    manifest_path: str | Path,
    *,
    expected_manifest_sha256: str,
    repo_root: str | Path,
    verify_raw: bool = True,
) -> PinnedPlumeDataset: ...
```

It raises `PinnedDatasetError` when:
- a file is missing;
- the manifest hash differs from `expected_manifest_sha256`;
- a listed raw or normalized hash or size differs;
- `record_count` differs;
- a record fails `PlumeObservation` validation;
- an ID is duplicated.

It reads only the files the manifest lists, never the whole global download. It must be deterministic and must not touch the network.

## Claude-1 side (DATA-02)

- **Config.** `SourcesConfig.plume_dataset: {manifest: <repo-relative path>, manifest_sha256: <hex>} | null`. It is part of `config_hash`, so a protocol lock binds the dataset. A `truth:` override of it is rejected. `null` is the documented synthetic-only mode: all sources are uniform fill. `configs/base.yaml` points at the pinned manifest once it exists. Families inherit it, so every policy and family sees the same records.
- **Runner.** `run_policy(bundle, policy_id, seed, *, plume_observations=())` stays the entry point (Claude-2's benchmark and gate call it unchanged). When the config names a dataset, the runner loads and verifies it once per process (cached by path and hash). Passing `plume_observations` explicitly while the config also names a dataset raises `ValueError`, so there are never two competing inputs. Source construction then stays as it is: region filter, 500 m clustering, then seeded uniform fill. It depends only on the plumes, the config and the seed, never on the policy.
- **Contract (additive).** `RunRecord.input_dataset: InputDatasetRef | None`, carrying `dataset_id`, `manifest_path`, `manifest_sha256`, `normalized_sha256`, `record_count`, `in_region_count`, `seeded_source_count` and `uniform_fill_count`. It is `None` in synthetic-only mode. The `DATA_READY` event repeats the counts. Claude-2's benchmark provenance can read `run.input_dataset`.
- **CLI.** `windows`, `simulate` and `benchmark` (through the runner) all use the config's dataset. `--synthetic-only` is an explicit switch on all three, and on the G4.5 gate, that sets `plume_dataset` to null; it appears in the output manifest or report. Run manifests (`lineage_version` 1) list repo-relative SHA-256 for the pinned ephemeris/EOP files, the dataset manifest, the normalized file and all 40 raw files. `export` re-verifies them against the record and the repository bytes, refuses missing, non-portable or altered evidence, and packs the dataset manifest and normalized records into the ZIP.
- **Truth.** Downloaded rates never set truth fluxes. Any prior-fitting from them needs Claude-2's review and a registered parameter change.
