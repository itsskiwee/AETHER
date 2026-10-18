# Completion batch: Codex-1 status (EMIT ingestion and local dataset)

Branch: `lane/ING-03-emit-dataset`. Ownership follows `Implementation/Six_Model_Completion_Prompt.md`:
`backend/aether/ingestion/`, `data/`, `DATA_LICENSES.md`, `CITATIONS.md`, and ingestion documentation/tests.

## Confirmed local inventory

- 1,686 metadata JSONs and 1,686 paired TIFFs; every JSON decodes and has one feature.
- `tiffinfo -D` read all 1,686 TIFFs without errors.
- 1,686 distinct provider IDs; no duplicates.
- Configured Permian bbox: 155 records, 73 numeric rates, 82 `NA` rates.
- Full download: 596 numeric rates and 1,090 `NA` rates.
- Exactly 144 connected components at the registered 500 m clustering distance among the 155 regional records.
- Stable inventory at `data/manifests/emit_inventory.json`, SHA-256 `c7f591ad79fd1f33fad2d30ffc0225642730d038ccfeeac6cb28c31fad24ff74`.
- Actual retrieval timestamp and per-file download URLs are unavailable. The raw-file commit timestamp establishes repository presence by then, not retrieval time. Manifest status will be `PARTIAL`; no time is inferred from filenames or filesystem metadata.
- The bulk download is removed from this branch's Git index and ignored, while all original local files remain in place. Earlier Git history still contains the pre-existing bulk-file commit; no history rewrite was performed.

## Waiting on Claude-1 contract adjustment

The pinned dataset interface requires `retrieved_at_utc: null` when the download time cannot be established, and normalized records must be serialized `PlumeObservation` objects. `DataSource.retrieved_at_utc` currently requires an aware datetime, so an honest normalized record cannot validate:

```python
DataSource(..., retrieved_at_utc=None, sha256="<metadata-file-sha256>")
# raises Pydantic ValidationError: Input should be a valid datetime
```

The user selected nullable retrieval time. Please change the shared `DataSource` contract to accept `datetime | None`; Codex-1 will keep its changes inside the ingestion lane. The dataset-level manifest retains the richer retrieval status, source URL list, and evidence note.

## Implementation and sample selection

- Added the exact observed V002 spaced-key aliases and parser coverage for rates, `NA`, timestamps, coordinates, source hash/identity, malformed features, and duplicate IDs.
- Added the pinned manifest loader with hash, size, path, record-count, identity, raw-pair, and duplicate checks.
- Added a deterministic local inventory command with TIFF full-read validation and 500 m source-cluster count. Re-running it produced the same inventory SHA-256.
- Selected 10 numeric-rate and 10 `NA` records by deterministic time-stratified sampling; all 20 coordinates fall into separate 500 m clusters. The preparer is implemented but correctly stops before writing because the shared `DataSource.retrieved_at_utc` contract still rejects `None`.
- Selected native IDs: `CH4_PlumeComplex-1451`, `CH4_PlumeComplex-1534`, `CH4_PlumeComplex-1782`, `CH4_PlumeComplex-1893`, `CH4_PlumeComplex-2138`, `CH4_PlumeComplex-219`, `CH4_PlumeComplex-2230`, `CH4_PlumeComplex-2249`, `CH4_PlumeComplex-2266`, `CH4_PlumeComplex-2703`, `CH4_PlumeComplex-2705`, `CH4_PlumeComplex-337`, `CH4_PlumeComplex-3372`, `CH4_PlumeComplex-3462`, `CH4_PlumeComplex-350`, `CH4_PlumeComplex-353`, `CH4_PlumeComplex-3638`, `CH4_PlumeComplex-399`, `CH4_PlumeComplex-404`, and `CH4_PlumeComplex-627`.
- The sample generator was run against the current contract and stopped before creating any sample directories/files, with the expected nullable-retrieval error.

## Verification and remaining dependency

- `python -m pytest`: 305 passed in 7m03s (only dependency deprecation warnings).
- `ruff check .`: passed. `ruff format --check .`: 71 files already formatted.
- `python -m aether.ingestion.inventory`: repeated output SHA-256 `c7f591ad79fd1f33fad2d30ffc0225642730d038ccfeeac6cb28c31fad24ff74`.
- Focused ingestion and source-construction tests passed (18 tests).
- The pinned sample, normalized export, and dataset manifest still await Claude-1's shared `DataSource.retrieved_at_utc: datetime | None` contract change. The contract file in that worktree still requires `UtcDatetime`.
