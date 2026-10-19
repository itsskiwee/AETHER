"""Offline inventory and integrity report for a local EMIT V002 download.

Run from the repository root with ``python -m aether.ingestion.inventory`` after installing
``aether[geo]``. The command reads local files only and emits a deterministic JSON inventory.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from aether.ingestion import (
    _emit_time_from_filename,
    _parse_emit_feature,
    _read_features,
    _RowError,
    cluster_to_sources,
    sha256_file,
)

DEFAULT_RAW_DIR = "data/raw/EMITL2BCH4PLM_002-20261018_042728"
DEFAULT_OUTPUT = "data/manifests/emit_inventory.json"
PERMIAN_BBOX_WGS84 = (-104.5, 30.8, -101.0, 33.5)


def build_local_inventory(
    raw_dir: str | Path,
    *,
    repo_root: str | Path,
    tiff_workers: int = 8,
) -> dict[str, Any]:
    """Inspect all paired local metadata and TIFF files without fetching or modifying them."""
    root = Path(repo_root).resolve()
    directory = Path(raw_dir)
    if not directory.is_absolute():
        directory = root / directory
    directory = directory.resolve()
    try:
        directory.relative_to(root)
    except ValueError as exc:
        raise ValueError("raw_dir must resolve inside repo_root") from exc
    if not directory.is_dir():
        raise FileNotFoundError(f"raw dataset directory not found: {directory}")
    if tiff_workers < 1:
        raise ValueError("tiff_workers must be positive")

    metadata_paths = sorted(directory.glob("*.json"), key=lambda path: path.name)
    tiff_paths = sorted(directory.glob("*.tif"), key=lambda path: path.name)
    tiff_by_name = {path.name: path for path in tiff_paths}
    tiffinfo = shutil.which("tiffinfo")
    tiff_checks = {}
    if tiffinfo:
        with ThreadPoolExecutor(max_workers=tiff_workers) as pool:
            checked = pool.map(
                lambda path: _read_tiff(path, tiffinfo, root),
                tiff_paths,
            )
            tiff_checks = {record["path"]: record for record in checked}

    entries: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    normalized: list[SimpleNamespace] = []
    first_by_native_id: dict[str, int] = {}
    for path in metadata_paths:
        rel_json = path.relative_to(root).as_posix()
        tiff_name = path.name.replace("CH4PLMMETA", "CH4PLM", 1).removesuffix(".json") + ".tif"
        tiff_path = tiff_by_name.get(tiff_name)
        item: dict[str, Any] = {
            "metadata": _file_record(path, root, "metadata"),
            "raster": _file_record(tiff_path, root, "raster") if tiff_path else None,
            "status": "REJECTED",
            "diagnostics": [],
        }
        if tiff_path is None:
            _add_diagnostic(item, "MISSING_TIFF_PAIR", f"no paired raster named {tiff_name}")
        elif tiffinfo:
            result = tiff_checks[tiff_path.relative_to(root).as_posix()]
            item["raster_read_check"] = result["status"]
            if result["status"] != "VALID":
                _add_diagnostic(item, result["code"], result["message"])
        else:
            item["raster_read_check"] = "UNVERIFIED"
            _add_diagnostic(item, "TIFFINFO_UNAVAILABLE", "tiffinfo executable was not found")

        features, document_diagnostics = _read_features(path)
        for diagnostic in document_diagnostics:
            _add_diagnostic(item, diagnostic.code, diagnostic.message, diagnostic.row)
        if len(features) != 1:
            _add_diagnostic(
                item,
                "EXPECTED_ONE_FEATURE",
                f"native metadata file contains {len(features)} valid features; expected one",
            )
        parsed: dict[str, Any] | None = None
        if len(features) == 1:
            try:
                parsed = _parse_emit_feature(features[0][1], _emit_time_from_filename(path.name))
            except (ValueError, TypeError, KeyError, _RowError) as exc:
                code = exc.code if isinstance(exc, _RowError) else "INVALID_FEATURE"
                _add_diagnostic(item, code, str(exc), features[0][0])

        if parsed is not None:
            native_id = parsed["native_id"]
            item.update(
                {
                    "native_id": native_id,
                    "acquisition_time_utc": parsed["acquisition_time_utc"]
                    .astimezone(UTC)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "lon": parsed["lon"],
                    "lat": parsed["lat"],
                    "emission_rate_kg_h": parsed["emission_rate_kg_h"],
                    "emission_rate_uncertainty_kg_h": parsed["emission_rate_uncertainty_kg_h"],
                    "uncertainty_kind": parsed["uncertainty_kind"].value,
                    "missing_rate_reason": (
                        parsed["missing_rate_reason"].value
                        if parsed["missing_rate_reason"] is not None
                        else None
                    ),
                    "in_region": _inside_region(parsed["lon"], parsed["lat"]),
                }
            )
            if native_id in first_by_native_id:
                previous = entries[first_by_native_id[native_id]]
                _add_diagnostic(item, "DUPLICATE_ID", f"duplicate provider plume id {native_id!r}")
                _add_diagnostic(
                    previous,
                    "DUPLICATE_ID",
                    f"provider plume id {native_id!r} also appears in {rel_json}",
                )
            else:
                first_by_native_id[native_id] = len(entries)
            if item["in_region"] and not item["diagnostics"]:
                normalized.append(
                    SimpleNamespace(
                        id=native_id,
                        acquisition_time_utc=parsed["acquisition_time_utc"],
                        lon=parsed["lon"],
                        lat=parsed["lat"],
                    )
                )
        entries.append(item)

    for item in entries:
        item["diagnostics"].sort(key=lambda d: (d["code"], d.get("row", -1), d["message"]))
        item["status"] = "ACCEPTED" if not item["diagnostics"] else "REJECTED"
        diagnostics.extend(
            {"path": item["metadata"]["path"], **diagnostic} for diagnostic in item["diagnostics"]
        )
    diagnostics.sort(key=lambda d: (d["path"], d["code"], d.get("row", -1), d["message"]))

    counts = Counter()
    regional_items = [item for item in entries if item.get("in_region")]
    for item in entries:
        if item["status"] == "ACCEPTED":
            counts["accepted_metadata_raster_pairs"] += 1
        else:
            counts["rejected_metadata_raster_pairs"] += 1
        if "emission_rate_kg_h" not in item:
            continue
        value = item["emission_rate_kg_h"]
        counts["numeric_rates"] += value is not None
        counts["null_rates"] += value is None
        reason = item.get("missing_rate_reason")
        if reason:
            counts[f"null_rate_reason:{reason}"] += 1
    counts["regional_metadata_records"] = len(regional_items)
    counts["regional_numeric_rates"] = sum(
        item.get("in_region") is True and item.get("emission_rate_kg_h") is not None
        for item in entries
    )
    counts["regional_null_rates"] = sum(
        item.get("in_region") is True and item.get("emission_rate_kg_h") is None for item in entries
    )
    regional_ids = [item["native_id"] for item in regional_items if "native_id" in item]
    counts["regional_unique_native_ids"] = len(set(regional_ids))
    try:
        counts["regional_clusters_at_500_m"] = len(cluster_to_sources(normalized, 500.0))
    except RuntimeError as exc:
        counts["regional_clusters_at_500_m"] = None
        diagnostics.append(
            {
                "path": "",
                "code": "GEO_DEPENDENCY_UNAVAILABLE",
                "message": str(exc),
            }
        )
    duplicate_ids = sorted(
        native_id for native_id, count in Counter(ids for ids in regional_ids).items() if count > 1
    )
    if tiffinfo:
        tiff_integrity = {
            "tool": "tiffinfo -D",
            "status": "COMPLETE"
            if all(item["status"] == "VALID" for item in tiff_checks.values())
            else "ERRORS",
            "checked_count": len(tiff_checks),
            "error_count": sum(item["status"] != "VALID" for item in tiff_checks.values()),
        }
    else:
        tiff_integrity = {
            "tool": "tiffinfo -D",
            "status": "UNAVAILABLE",
            "checked_count": 0,
            "error_count": None,
        }

    return {
        "schema_version": 1,
        "dataset_id": "emit-l2b-ch4plm-002-local-inventory",
        "provider": "NASA LP DAAC",
        "dataset": "EMITL2BCH4PLM",
        "version": "002",
        "raw_directory": directory.relative_to(root).as_posix(),
        "region_bbox_wgs84": list(PERMIAN_BBOX_WGS84),
        "tiff_integrity": tiff_integrity,
        "summary": {
            "metadata_json_count": len(metadata_paths),
            "tiff_count": len(tiff_paths),
            "unmatched_tiff_count": len(
                set(tiff_by_name) - {_paired_tiff_name(p.name) for p in metadata_paths}
            ),
            "total_raw_bytes": sum(p.stat().st_size for p in metadata_paths + tiff_paths),
            "unique_native_ids": len(first_by_native_id),
            "duplicate_native_ids": duplicate_ids,
            "counts": dict(sorted(counts.items())),
            "accepted_rejected_diagnostics": diagnostics,
        },
        "files": entries,
    }


def write_inventory(
    inventory: dict[str, Any], output_path: str | Path, *, repo_root: str | Path
) -> str:
    """Write stable, sorted-key JSON and return its SHA-256."""
    import hashlib

    root = Path(repo_root).resolve()
    output = Path(output_path)
    if not output.is_absolute():
        output = root / output
    output = output.resolve()
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise ValueError("output_path must resolve inside repo_root") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(inventory, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    output.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _read_tiff(path: Path, executable: str, repo_root: Path) -> dict[str, Any]:
    run = subprocess.run(
        [executable, "-D", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    relative = path.relative_to(repo_root).as_posix()
    if run.returncode == 0:
        return {"path": relative, "status": "VALID", "code": None, "message": ""}
    message = (run.stderr or run.stdout or f"tiffinfo exited {run.returncode}").strip()
    message = message.replace(path.as_posix(), relative)
    return {"path": relative, "status": "INVALID", "code": "TIFF_READ_ERROR", "message": message}


def _file_record(path: Path | None, root: Path, role: str) -> dict[str, Any] | None:
    if path is None:
        return None
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "role": role,
    }


def _paired_tiff_name(metadata_name: str) -> str:
    return metadata_name.replace("CH4PLMMETA", "CH4PLM", 1).removesuffix(".json") + ".tif"


def _inside_region(lon: float, lat: float) -> bool:
    lon_min, lat_min, lon_max, lat_max = PERMIAN_BBOX_WGS84
    return lon_min <= lon <= lon_max and lat_min <= lat <= lat_max


def _add_diagnostic(item: dict[str, Any], code: str, message: str, row: int | None = None) -> None:
    diagnostic = {"code": code, "message": message}
    if row is not None:
        diagnostic["row"] = row
    item["diagnostics"].append(diagnostic)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Inventory local NASA EMIT V002 metadata and TIFFs"
    )
    parser.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--tiff-workers", type=int, default=8)
    args = parser.parse_args()

    inventory = build_local_inventory(
        args.raw_dir,
        repo_root=repo_root,
        tiff_workers=args.tiff_workers,
    )
    digest = write_inventory(inventory, args.output, repo_root=repo_root)
    print(f"inventory: {args.output}")
    print(f"sha256: {digest}")
    print(json.dumps(inventory["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
