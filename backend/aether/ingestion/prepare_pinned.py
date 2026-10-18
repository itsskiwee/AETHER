"""Build the small, reproducible Permian sample from a previously generated local inventory.

This command does not fetch data, infer fluxes from rasters, or infer present-day activity. The
local inventory and selected upstream files are read-only inputs; only the 20 selected raw pairs,
normalized observations, and manifest are written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from aether.contracts.models import DataSource
from aether.ingestion import (
    ADAPTER_VERSION,
    TRANSFORMATION_VERSION,
    cluster_to_sources,
    parse_emit_plume_geojson,
    sha256_file,
)

DATASET_ID = "emit-l2b-ch4plm-002-permian-v1"
PRODUCT_URL = "https://doi.org/10.5067/EMIT/EMITL2BCH4PLM.002"
CATALOG_URL = "https://data.nasa.gov/dataset/emit-l2b-estimated-methane-plume-complexes-60-m-v002"
LICENSE_URL = "https://www.usa.gov/government-works"
CITATION = (
    "Green, R. O., et al. EMIT L2B Estimated Methane Plume Complexes 60 m V002. "
    "NASA Land Processes Distributed Active Archive Center. "
    "https://doi.org/10.5067/EMIT/EMITL2BCH4PLM.002"
)
RETRIEVAL_EVIDENCE = (
    "The product DOI and NASA catalog URL are known, but exact per-file download URLs and the "
    "actual retrieval timestamp were not retained. Git history shows these input bytes were "
    "present by commit a70976e8306e82e99d055eadfa6056f12022b125 (2026-10-18T04:59:19Z); that is "
    "repository-inclusion evidence only, not a retrieval timestamp. Filename and filesystem "
    "timestamps are not used to fill the gap."
)
SELECTION_RULE = (
    "Use accepted unique metadata/raster pairs whose representative coordinates fall inside the "
    "registered Permian bbox. Partition by finite numeric rate versus provider literal NA. Sort "
    "each stratum by (UTC Time Observed, Plume ID); for each of ten positions i=0..9, select "
    "index floor((i + 0.5) * stratum_count / 10). Merge the strata and normalize by id."
)


def prepare_pinned_dataset(
    *,
    repo_root: str | Path,
    inventory_path: str | Path = "data/manifests/emit_inventory.json",
    raw_output_dir: str | Path = "data/raw/pinned_emit_permian_v1",
    normalized_path: str | Path = "data/normalized/emit_permian_plumes.json",
    manifest_path: str | Path = "data/manifests/emit_permian.json",
) -> dict[str, Any]:
    """Select and write the versioned 20-record input and its content manifest."""
    root = Path(repo_root).resolve()
    try:
        DataSource(
            provider="NASA LP DAAC",
            dataset="EMITL2BCH4PLM",
            version="002",
            url=PRODUCT_URL,
            license_url=LICENSE_URL,
            citation_text=CITATION,
            retrieved_at_utc=None,
            sha256="0" * 64,
        )
    except Exception as exc:
        raise RuntimeError(
            "DataSource.retrieved_at_utc must accept null before preparing this dataset; "
            "actual retrieval time is unavailable"
        ) from exc
    inventory_file = _resolve(root, inventory_path)
    inventory_bytes = inventory_file.read_bytes()
    inventory_sha256 = hashlib.sha256(inventory_bytes).hexdigest()
    inventory = json.loads(inventory_bytes)
    rows = inventory["files"]
    if any(row.get("status") != "ACCEPTED" for row in rows):
        raise ValueError("local inventory contains rejected metadata/raster pairs")

    regional = [row for row in rows if row.get("in_region") is True]
    numeric = [row for row in regional if row.get("emission_rate_kg_h") is not None]
    missing = [row for row in regional if row.get("emission_rate_kg_h") is None]
    selected = _stratified_ten(numeric) + _stratified_ten(missing)
    selected.sort(key=lambda row: row["native_id"])
    if len({row["native_id"] for row in selected}) != 20:
        raise ValueError("deterministic sample did not produce 20 unique native IDs")

    raw_dir = _resolve(root, raw_output_dir, must_exist=False)
    normalized_file = _resolve(root, normalized_path, must_exist=False)
    manifest_file = _resolve(root, manifest_path, must_exist=False)
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)

    normalized_records = []
    raw_files = []
    source_clusters = []
    for row in selected:
        native_id = row["native_id"]
        metadata_source = _resolve(root, row["metadata"]["path"])
        raster_source = _resolve(root, row["raster"]["path"])
        metadata_target = raw_dir / metadata_source.name
        raster_target = raw_dir / raster_source.name
        _copy_unchanged(metadata_source, metadata_target)
        _copy_unchanged(raster_source, raster_target)

        source = DataSource(
            provider="NASA LP DAAC",
            dataset="EMITL2BCH4PLM",
            version="002",
            url=PRODUCT_URL,
            license_url=LICENSE_URL,
            citation_text=CITATION,
            retrieved_at_utc=None,
            sha256=sha256_file(metadata_target),
        )
        plumes, diagnostics = parse_emit_plume_geojson(metadata_target, source)
        if diagnostics or len(plumes) != 1 or plumes[0].native_id != native_id:
            raise ValueError(
                f"selected native ID {native_id!r} failed parser validation: {diagnostics!r}"
            )
        plume = plumes[0]
        normalized_records.append(plume.model_dump(mode="json"))
        source_clusters.append(
            SimpleNamespace(
                id=plume.id,
                acquisition_time_utc=plume.acquisition_time_utc,
                lon=plume.lon,
                lat=plume.lat,
            )
        )
        raw_files.extend(
            [
                _raw_file_record(metadata_target, root, "metadata", native_id),
                _raw_file_record(raster_target, root, "raster", native_id),
            ]
        )

    normalized_records.sort(key=lambda record: record["id"])
    normalized_bytes = _json_bytes(normalized_records)
    normalized_file.write_bytes(normalized_bytes)
    raw_files.sort(key=lambda record: (record["native_id"], record["role"], record["path"]))

    manifest = {
        "schema_version": 1,
        "dataset_id": DATASET_ID,
        "provider": "NASA LP DAAC",
        "dataset": "EMITL2BCH4PLM",
        "version": "002",
        "citation_text": CITATION,
        "license_url": LICENSE_URL,
        "catalog_url": CATALOG_URL,
        "retrieval": {
            "status": "PARTIAL",
            "retrieved_at_utc": None,
            "source_urls": [],
            "evidence": RETRIEVAL_EVIDENCE,
        },
        "selection": {
            "region_bbox_wgs84": list(inventory["region_bbox_wgs84"]),
            "rule": SELECTION_RULE,
            "inventory_path": Path(inventory_path).as_posix(),
            "inventory_sha256": inventory_sha256,
            "regional_inventory_count": len(regional),
            "regional_numeric_rate_count": len(numeric),
            "regional_na_rate_count": len(missing),
            "selected_numeric_rate_count": len(
                numeric_records := [
                    record
                    for record in normalized_records
                    if record["emission_rate_kg_h"] is not None
                ]
            ),
            "selected_na_rate_count": len(normalized_records) - len(numeric_records),
            "regional_500_m_cluster_count": inventory["summary"]["counts"][
                "regional_clusters_at_500_m"
            ],
            "selected_500_m_cluster_count": len(cluster_to_sources(source_clusters, 500.0)),
            "selected_native_ids": [
                record["native_id"] for record in raw_files if record["role"] == "metadata"
            ],
        },
        "adapter_version": ADAPTER_VERSION,
        "transformation_version": TRANSFORMATION_VERSION,
        "raw_files": raw_files,
        "normalized": {
            "path": Path(normalized_path).as_posix(),
            "sha256": hashlib.sha256(normalized_bytes).hexdigest(),
            "size_bytes": len(normalized_bytes),
            "record_count": len(normalized_records),
        },
        "known_limitations": [
            "EMIT V002 is a plume product; missing plume rows are not non-detections.",
            (
                "These 2022-2025 records provide historical location context only and never set "
                "2026 simulated truth or activity."
            ),
            (
                "Native rate uncertainty values are retained, but uncertainty_kind remains "
                "UNKNOWN pending scientific review."
            ),
            (
                "The 20-record deterministic time-stratified sample is not a probability sample "
                "of all Permian sources."
            ),
            "Exact file retrieval URLs and retrieval time are unavailable; see retrieval.evidence.",
        ],
    }
    manifest_bytes = _json_bytes(manifest)
    manifest_file.write_bytes(manifest_bytes)
    manifest["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    return manifest


def _stratified_ten(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: (row["acquisition_time_utc"], row["native_id"]))
    if len(ordered) < 10:
        raise ValueError("each rate-status stratum needs at least 10 regional records")
    selected = []
    for index in range(10):
        rank = math.floor((index + 0.5) * len(ordered) / 10)
        selected.append(ordered[rank])
    return selected


def _raw_file_record(path: Path, root: Path, role: str, native_id: str) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "role": role,
        "native_id": native_id,
    }


def _copy_unchanged(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256_file(source) != sha256_file(destination):
            raise ValueError(f"refusing to overwrite changed pinned input {destination}")
        return
    shutil.copyfile(source, destination)
    if sha256_file(source) != sha256_file(destination):
        raise ValueError(f"copied input hash mismatch for {destination}")


def _resolve(root: Path, value: str | Path, *, must_exist: bool = True) -> Path:
    path = Path(value)
    resolved = (path if path.is_absolute() else root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path must stay inside repository: {value}") from exc
    if must_exist and not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description=("Prepare the pinned historical EMIT Permian sample")
    )
    parser.add_argument("--inventory", default="data/manifests/emit_inventory.json")
    parser.add_argument("--raw-output", default="data/raw/pinned_emit_permian_v1")
    parser.add_argument("--normalized", default="data/normalized/emit_permian_plumes.json")
    parser.add_argument("--manifest", default="data/manifests/emit_permian.json")
    args = parser.parse_args()
    manifest = prepare_pinned_dataset(
        repo_root=repo_root,
        inventory_path=args.inventory,
        raw_output_dir=args.raw_output,
        normalized_path=args.normalized,
        manifest_path=args.manifest,
    )
    print(f"dataset_id: {manifest['dataset_id']}")
    print(f"normalized_sha256: {manifest['normalized']['sha256']}")
    print(f"manifest_sha256: {manifest['manifest_sha256']}")
    print(f"records: {manifest['normalized']['record_count']}")


if __name__ == "__main__":
    main()
