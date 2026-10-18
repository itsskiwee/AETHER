"""The checked-in pinned EMIT Permian sample (DATA-01), verified offline and independently.

These tests read the tracked files a fresh checkout contains. They re-derive each normalized
record from its raw provider JSON with the standard library only, so a parser change cannot
silently rewrite the pinned input. The bulk download is optional: checks against it are skipped
when it is absent (it is ignored by git).
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from itertools import combinations
from pathlib import Path

import pytest

from aether.config import load_scenario
from aether.contracts.enums import MissingReason, ProvenanceClass, UncertaintyKind
from aether.ingestion import PinnedDatasetError, load_pinned_plume_dataset

REPO = Path(__file__).resolve().parents[3]
MANIFEST = "data/manifests/emit_permian.json"
BULK_DIR = REPO / "data/raw/EMITL2BCH4PLM_002-20261018_042728"
RATE_KEY = "Emissions Rate Estimate (kg/hr)"
UNCERTAINTY_KEY = "Emissions Rate Estimate Uncertainty (kg/hr)"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest() -> dict:
    return json.loads((REPO / MANIFEST).read_text(encoding="utf-8"))


def _configured_sha() -> str:
    spec = load_scenario(REPO / "configs/base.yaml").model.sources.plume_dataset
    assert spec is not None and spec.manifest == MANIFEST
    return spec.manifest_sha256


def _normalized() -> list[dict]:
    return json.loads((REPO / _manifest()["normalized"]["path"]).read_text(encoding="utf-8"))


def test_base_config_pins_the_checked_in_manifest_and_it_loads_offline():
    expected = _configured_sha()
    assert _sha(REPO / MANIFEST) == expected
    dataset = load_pinned_plume_dataset(
        MANIFEST, expected_manifest_sha256=expected, repo_root=REPO
    )
    assert dataset.dataset_id == "emit-l2b-ch4plm-002-permian-v1"
    assert dataset.manifest_path == MANIFEST
    assert len(dataset.plumes) == 20 and dataset.raw_file_count == 40
    assert all(p.provenance_class is ProvenanceClass.REAL_OBSERVATION for p in dataset.plumes)


def test_every_listed_file_is_tracked_sized_and_hashed():
    manifest = _manifest()
    for record in manifest["raw_files"]:
        path = REPO / record["path"]
        assert path.is_file(), record["path"]
        assert record["path"].startswith("data/raw/pinned_emit_permian_v1/")
        assert path.stat().st_size == record["size_bytes"]
        assert _sha(path) == record["sha256"]
    normalized = REPO / manifest["normalized"]["path"]
    assert _sha(normalized) == manifest["normalized"]["sha256"]
    assert normalized.stat().st_size == manifest["normalized"]["size_bytes"]
    roles = {}
    for record in manifest["raw_files"]:
        roles.setdefault(record["native_id"], []).append(record["role"])
    assert all(sorted(r) == ["metadata", "raster"] for r in roles.values())
    assert len(roles) == 20


def test_normalized_records_rederive_from_raw_json_without_the_parser():
    manifest = _manifest()
    metadata = {r["native_id"]: r for r in manifest["raw_files"] if r["role"] == "metadata"}
    records = _normalized()
    assert [r["id"] for r in records] == sorted(r["id"] for r in records)
    assert len({r["id"] for r in records}) == len(records) == 20
    for record in records:
        raw_ref = metadata[record["native_id"]]
        raw = json.loads((REPO / raw_ref["path"]).read_text(encoding="utf-8"))
        assert raw["type"] == "FeatureCollection" and len(raw["features"]) == 1
        props = raw["features"][0]["properties"]
        assert props["Plume ID"] == record["native_id"]
        assert record["id"] == f"NASA LP DAAC:{record['native_id']}"
        assert record["acquisition_time_utc"] == props["UTC Time Observed"]
        assert record["lon"] == props["Longitude of max concentration"]
        assert record["lat"] == props["Latitude of max concentration"]
        assert record["raw_properties"] == props
        assert record["provenance_class"] == ProvenanceClass.REAL_OBSERVATION.value
        assert record["uncertainty_kind"] == UncertaintyKind.UNKNOWN.value
        # kg/hr and kg/h are the same unit: the value is carried over unchanged, never scaled.
        if props[RATE_KEY] == "NA":
            assert record["emission_rate_kg_h"] is None
            assert record["missing_rate_reason"] == MissingReason.CRITERIA_NOT_MET.value
        else:
            assert record["emission_rate_kg_h"] == props[RATE_KEY]
            assert record["missing_rate_reason"] is None
        if props[UNCERTAINTY_KEY] == "NA":
            assert record["emission_rate_uncertainty_kg_h"] is None
        else:
            assert record["emission_rate_uncertainty_kg_h"] == props[UNCERTAINTY_KEY]
        source = record["source"]
        assert source["sha256"] == raw_ref["sha256"]
        assert "retrieved_at_utc" in source and source["retrieved_at_utc"] is None
        assert (source["provider"], source["dataset"], source["version"]) == (
            "NASA LP DAAC",
            "EMITL2BCH4PLM",
            "002",
        )


def test_sample_is_regional_balanced_and_in_distinct_500_m_clusters():
    pyproj = pytest.importorskip("pyproj")
    manifest = _manifest()
    lon_min, lat_min, lon_max, lat_max = manifest["selection"]["region_bbox_wgs84"]
    records = _normalized()
    assert all(lon_min <= r["lon"] <= lon_max and lat_min <= r["lat"] <= lat_max for r in records)
    numeric = [r for r in records if r["emission_rate_kg_h"] is not None]
    assert len(numeric) == 10 and len(records) - len(numeric) == 10
    geod = pyproj.Geod(ellps="WGS84")
    closest = min(
        geod.inv(a["lon"], a["lat"], b["lon"], b["lat"])[2] for a, b in combinations(records, 2)
    )
    assert closest > 500.0
    selection = manifest["selection"]
    assert selection["selected_500_m_cluster_count"] == 20
    assert (selection["regional_inventory_count"], selection["regional_numeric_rate_count"]) == (
        155,
        73,
    )
    assert selection["regional_na_rate_count"] == 82
    assert selection["regional_500_m_cluster_count"] == 144


def test_selection_rule_recomputed_from_the_inventory():
    manifest = _manifest()
    inventory_path = REPO / manifest["selection"]["inventory_path"]
    assert _sha(inventory_path) == manifest["selection"]["inventory_sha256"]
    rows = [r for r in json.loads(inventory_path.read_text())["files"] if r["in_region"]]
    picked = []
    for stratum in (
        [r for r in rows if r["emission_rate_kg_h"] is not None],
        [r for r in rows if r["emission_rate_kg_h"] is None],
    ):
        ordered = sorted(stratum, key=lambda r: (r["acquisition_time_utc"], r["native_id"]))
        picked += [ordered[math.floor((i + 0.5) * len(ordered) / 10)] for i in range(10)]
    assert sorted(r["native_id"] for r in picked) == manifest["selection"]["selected_native_ids"]
    by_id = {r["native_id"]: r for r in picked}
    for record in manifest["raw_files"]:
        assert record["sha256"] == by_id[record["native_id"]][record["role"]]["sha256"]


def test_retrieval_facts_are_recorded_as_unknown_not_reconstructed():
    retrieval = _manifest()["retrieval"]
    assert retrieval["status"] == "PARTIAL"
    assert retrieval["retrieved_at_utc"] is None
    assert retrieval["source_urls"] == []
    assert "not a retrieval timestamp" in retrieval["evidence"]


@pytest.mark.skipif(not BULK_DIR.is_dir(), reason="bulk EMIT download is local-only")
def test_pinned_copies_are_byte_identical_to_the_local_originals():
    for record in _manifest()["raw_files"]:
        original = BULK_DIR / Path(record["path"]).name
        assert original.is_file(), original
        assert _sha(original) == record["sha256"]


def _copy_sample(tmp_path: Path) -> Path:
    manifest = _manifest()
    paths = [
        MANIFEST,
        manifest["normalized"]["path"],
        *(r["path"] for r in manifest["raw_files"]),
    ]
    for rel in paths:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target)
    return tmp_path


def _load(root: Path):
    return load_pinned_plume_dataset(
        MANIFEST, expected_manifest_sha256=_configured_sha(), repo_root=root
    )


def test_copied_sample_loads_outside_the_repository(tmp_path):
    assert len(_load(_copy_sample(tmp_path)).plumes) == 20


@pytest.mark.parametrize("role", ["metadata", "raster"])
def test_tampered_raw_file_fails_clearly(tmp_path, role):
    root = _copy_sample(tmp_path)
    record = next(r for r in _manifest()["raw_files"] if r["role"] == role)
    path = root / record["path"]
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0x01
    path.write_bytes(bytes(data))
    with pytest.raises(PinnedDatasetError, match="SHA-256 mismatch"):
        _load(root)


def test_missing_raw_file_fails_clearly(tmp_path):
    root = _copy_sample(tmp_path)
    (root / _manifest()["raw_files"][0]["path"]).unlink()
    with pytest.raises(PinnedDatasetError, match="missing"):
        _load(root)


def test_tampered_normalized_record_fails_clearly(tmp_path):
    root = _copy_sample(tmp_path)
    path = root / _manifest()["normalized"]["path"]
    records = json.loads(path.read_text())
    records[0]["emission_rate_kg_h"] = 1.0e6
    path.write_text(json.dumps(records, sort_keys=True, indent=2) + "\n")
    with pytest.raises(PinnedDatasetError, match="normalized input SHA-256 mismatch"):
        _load(root)


def test_edited_manifest_fails_before_any_listed_path_is_trusted(tmp_path):
    root = _copy_sample(tmp_path)
    path = root / MANIFEST
    path.write_bytes(path.read_bytes().replace(b'"PARTIAL"', b'"AUTHENTIC"'))
    with pytest.raises(PinnedDatasetError, match="manifest SHA-256 mismatch"):
        _load(root)
