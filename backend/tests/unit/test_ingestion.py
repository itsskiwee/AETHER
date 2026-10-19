import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from aether.contracts.enums import MissingReason, UncertaintyKind
from aether.contracts.models import DataSource, PlumeObservation
from aether.ingestion import (
    PinnedDatasetError,
    _emit_rate_uncertainty_kind,
    _missing_rate_reason,
    cluster_to_sources,
    load_pinned_plume_dataset,
    parse_emit_plume_geojson,
    sha256_file,
)
from aether.ingestion import inventory as ingestion_inventory
from aether.ingestion.prepare_pinned import _stratified_ten


def test_small_plume_set_clusters_deterministically():
    pytest.importorskip("pyproj")
    observed_at = datetime(2026, 10, 17, tzinfo=UTC)
    plumes = [
        SimpleNamespace(
            id=native_id,
            acquisition_time_utc=observed_at,
            lon=lon,
            lat=31.0,
        )
        for native_id, lon in (
            ("p3", -102.0),
            ("p1", -103.0),
            ("p2", -102.999),
        )
    ]

    first = cluster_to_sources(plumes, min_separation_m=500.0)
    second = cluster_to_sources(list(reversed(plumes)), min_separation_m=500.0)

    assert len(plumes) < 20
    assert [item.model_dump(mode="json") for item in first] == [
        item.model_dump(mode="json") for item in second
    ]
    assert len(first) == 2
    assert {item.seeded_from_plume_id for item in first} == {"p1", "p3"}


def test_emit_synthetic_fixture_stays_example_only(repo_root):
    fixture = repo_root / "data/fixtures/emit_v002_synthetic.geojson"
    source = DataSource(
        provider="NASA LP DAAC",
        dataset="EMIT L2B Estimated Methane Plume Complexes 60 m V002",
        version="002",
        url="https://example.invalid/synthetic-fixture",
        license_url=None,
        citation_text="Fabricated offline parser example; not provider data.",
        retrieved_at_utc=datetime(2026, 10, 17, tzinfo=UTC),
        sha256=sha256_file(fixture),
    )

    plumes, diagnostics = parse_emit_plume_geojson(fixture, source)

    assert plumes == []
    assert [diagnostic.code for diagnostic in diagnostics] == ["EXAMPLE_FIXTURE_NOT_REAL_DATA"]


def test_carbon_mapper_has_no_stored_records_or_fixtures(repo_root):
    fixtures = list((repo_root / "data/fixtures").glob("*carbon_mapper*"))
    manifest = json.loads(
        (repo_root / "data/manifests/synthetic_ingestion_examples.json").read_text()
    )

    assert fixtures == []
    assert all("carbon_mapper" not in record["path"].casefold() for record in manifest["files"])


def test_emit_malformed_feature_yields_row_diagnostic_without_observation(tmp_path):
    input_path = tmp_path / "offline-malformed-input.geojson"
    input_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "bad-polygon",
                        "properties": {
                            "Plume_ID": "bad-polygon",
                            "datetime": "2023-08-14T18:02:00Z",
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    source = DataSource(
        provider="NASA LP DAAC",
        dataset="EMIT L2B Estimated Methane Plume Complexes 60 m V002",
        version="002",
        url="https://example.invalid/offline-unit-input",
        license_url=None,
        citation_text="Malformed offline parser test input; no provider data.",
        retrieved_at_utc=datetime(2026, 10, 17, tzinfo=UTC),
        sha256=sha256_file(input_path),
    )

    plumes, diagnostics = parse_emit_plume_geojson(input_path, source)

    assert plumes == []
    assert [(item.row, item.feature_id, item.code) for item in diagnostics] == [
        (0, "bad-polygon", "INVALID_GEOMETRY")
    ]


def test_emit_missing_values_keep_explicit_semantics():
    assert _missing_rate_reason("N/A", None) is MissingReason.CRITERIA_NOT_MET
    assert _missing_rate_reason(None, None) is MissingReason.NOT_PROVIDED
    assert _emit_rate_uncertainty_kind({}, None) is UncertaintyKind.UNKNOWN


def test_emit_native_v002_fields_preserve_rates_nulls_and_raw_properties(tmp_path):
    features = [
        _native_emit_feature(
            "CH4_PlumeComplex-42",
            {
                "UTC Time Observed": "2024-10-23T08:37:41Z",
                "Latitude of max concentration": 32.25,
                "Longitude of max concentration": -103.5,
                "Max Plume Concentration (ppm m)": 3264.0,
                "Emissions Rate Estimate (kg/hr)": 3264.4358,
                "Emissions Rate Estimate Uncertainty (kg/hr)": 673.7789,
            },
        ),
        _native_emit_feature(
            "CH4_PlumeComplex-43",
            {
                "UTC Time Observed": "2024-10-23T08:37:41Z",
                "Latitude of max concentration": 32.5,
                "Longitude of max concentration": -103.25,
                "Max Plume Concentration (ppm m)": 7677.0,
                "Emissions Rate Estimate (kg/hr)": "NA",
                "Emissions Rate Estimate Uncertainty (kg/hr)": "NA",
            },
        ),
    ]
    path = _write_emit_document(tmp_path / "native-v002.geojson", features)
    source = _emit_source(path)

    plumes, diagnostics = parse_emit_plume_geojson(path, source)

    assert diagnostics == []
    assert [plume.native_id for plume in plumes] == [
        "CH4_PlumeComplex-42",
        "CH4_PlumeComplex-43",
    ]
    estimated, missing = plumes
    assert estimated.acquisition_time_utc == datetime(2024, 10, 23, 8, 37, 41, tzinfo=UTC)
    assert (estimated.lon, estimated.lat) == (-103.5, 32.25)
    assert estimated.emission_rate_kg_h == 3264.4358
    assert estimated.emission_rate_uncertainty_kg_h == 673.7789
    assert estimated.uncertainty_kind is UncertaintyKind.UNKNOWN
    assert estimated.raw_properties["Max Plume Concentration (ppm m)"] == 3264.0
    assert missing.emission_rate_kg_h is None
    assert missing.emission_rate_uncertainty_kg_h is None
    assert missing.missing_rate_reason is MissingReason.CRITERIA_NOT_MET
    assert missing.uncertainty_kind is UncertaintyKind.UNKNOWN


def test_emit_duplicate_native_ids_keep_first_and_report_later_row(tmp_path):
    props = {
        "UTC Time Observed": "2024-10-23T08:37:41Z",
        "Latitude of max concentration": 32.25,
        "Longitude of max concentration": -103.5,
        "Emissions Rate Estimate (kg/hr)": "NA",
        "Emissions Rate Estimate Uncertainty (kg/hr)": "NA",
    }
    path = _write_emit_document(
        tmp_path / "duplicate-v002.geojson",
        [
            _native_emit_feature("CH4_PlumeComplex-42", props),
            _native_emit_feature("CH4_PlumeComplex-42", props),
        ],
    )

    plumes, diagnostics = parse_emit_plume_geojson(path, _emit_source(path))

    assert [plume.native_id for plume in plumes] == ["CH4_PlumeComplex-42"]
    assert [(item.row, item.code) for item in diagnostics] == [(1, "DUPLICATE_ID")]


def test_emit_source_identity_and_input_hash_are_checked(tmp_path):
    path = _write_emit_document(
        tmp_path / "native-v002.geojson",
        [
            _native_emit_feature(
                "CH4_PlumeComplex-42",
                {
                    "UTC Time Observed": "2024-10-23T08:37:41Z",
                    "Latitude of max concentration": 32.25,
                    "Longitude of max concentration": -103.5,
                    "Emissions Rate Estimate (kg/hr)": "NA",
                    "Emissions Rate Estimate Uncertainty (kg/hr)": "NA",
                },
            )
        ],
    )
    source = _emit_source(path)

    mismatch_hash = source.model_copy(update={"sha256": "0" * 64})
    _, hash_diagnostics = parse_emit_plume_geojson(path, mismatch_hash)
    mismatch_identity = source.model_copy(update={"provider": "Other provider"})
    _, identity_diagnostics = parse_emit_plume_geojson(path, mismatch_identity)

    assert [item.code for item in hash_diagnostics] == ["SOURCE_HASH_MISMATCH"]
    assert [item.code for item in identity_diagnostics] == ["SOURCE_IDENTITY_MISMATCH"]


def _native_emit_feature(native_id, properties):
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-103.51, 32.24],
                    [-103.49, 32.24],
                    [-103.49, 32.26],
                    [-103.51, 32.26],
                    [-103.51, 32.24],
                ]
            ],
        },
        "properties": {"Plume ID": native_id, **properties},
    }


def _write_emit_document(path, features):
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "crs": {
                    "type": "name",
                    "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
                },
                "features": features,
            }
        ),
        encoding="utf-8",
    )
    return path


def _emit_source(path):
    return DataSource(
        provider="NASA LP DAAC",
        dataset="EMITL2BCH4PLM",
        version="002",
        url="https://doi.org/10.5067/EMIT/EMITL2BCH4PLM.002",
        license_url="https://www.usa.gov/government-works",
        citation_text="EMIT L2B Estimated Methane Plume Complexes 60 m V002.",
        retrieved_at_utc=datetime(2026, 10, 18, tzinfo=UTC),
        sha256=sha256_file(path),
    )


def test_load_pinned_dataset_verifies_manifest_normalized_and_raw_inputs(tmp_path):
    manifest_path, manifest_sha256 = _write_pinned_dataset(tmp_path)

    dataset = load_pinned_plume_dataset(
        manifest_path,
        expected_manifest_sha256=manifest_sha256,
        repo_root=tmp_path,
    )

    assert dataset.dataset_id == "emit-l2b-ch4plm-002-permian-v1"
    assert dataset.manifest_path == "data/manifests/emit_permian.json"
    assert dataset.raw_file_count == 2
    assert [plume.id for plume in dataset.plumes] == ["NASA LP DAAC:p1"]
    absolute_dataset = load_pinned_plume_dataset(
        tmp_path / manifest_path,
        expected_manifest_sha256=manifest_sha256,
        repo_root=tmp_path,
    )
    assert absolute_dataset == dataset


def test_load_pinned_dataset_rejects_wrong_manifest_digest(tmp_path):
    manifest_path, _ = _write_pinned_dataset(tmp_path)

    with pytest.raises(PinnedDatasetError, match="manifest SHA-256 mismatch"):
        load_pinned_plume_dataset(
            manifest_path,
            expected_manifest_sha256="0" * 64,
            repo_root=tmp_path,
        )


def test_load_pinned_dataset_rejects_changed_raw_input(tmp_path):
    manifest_path, manifest_sha256 = _write_pinned_dataset(tmp_path)
    (tmp_path / "data/raw/p1.tif").write_bytes(b"changed raster")

    with pytest.raises(PinnedDatasetError, match="raw file size mismatch"):
        load_pinned_plume_dataset(
            manifest_path,
            expected_manifest_sha256=manifest_sha256,
            repo_root=tmp_path,
        )


def test_load_pinned_dataset_rejects_duplicate_normalized_ids(tmp_path):
    manifest_path, manifest_sha256 = _write_pinned_dataset(tmp_path, duplicate_record=True)

    with pytest.raises(PinnedDatasetError, match="duplicate normalized plume id"):
        load_pinned_plume_dataset(
            manifest_path,
            expected_manifest_sha256=manifest_sha256,
            repo_root=tmp_path,
        )


def test_load_pinned_dataset_rejects_incomplete_raw_pair(tmp_path):
    manifest_path, _ = _write_pinned_dataset(tmp_path)
    _rewrite_manifest(tmp_path, manifest_path, lambda manifest: manifest["raw_files"].pop())
    manifest_digest = sha256_file(tmp_path / manifest_path)

    with pytest.raises(PinnedDatasetError, match="exactly one metadata and raster"):
        load_pinned_plume_dataset(
            manifest_path,
            expected_manifest_sha256=manifest_digest,
            repo_root=tmp_path,
        )


def test_load_pinned_dataset_rejects_source_identity_mismatch(tmp_path):
    manifest_path, _ = _write_pinned_dataset(tmp_path)

    def mismatch_source_dataset(manifest):
        normalized_path = tmp_path / manifest["normalized"]["path"]
        records = json.loads(normalized_path.read_text(encoding="utf-8"))
        records[0]["source"]["dataset"] = "DIFFERENT_PRODUCT"
        normalized_bytes = (json.dumps(records, sort_keys=True, indent=2) + "\n").encode("utf-8")
        normalized_path.write_bytes(normalized_bytes)
        manifest["normalized"]["sha256"] = hashlib.sha256(normalized_bytes).hexdigest()
        manifest["normalized"]["size_bytes"] = len(normalized_bytes)

    _rewrite_manifest(tmp_path, manifest_path, mismatch_source_dataset)
    manifest_digest = sha256_file(tmp_path / manifest_path)

    with pytest.raises(PinnedDatasetError, match="source identity.*differs from manifest"):
        load_pinned_plume_dataset(
            manifest_path,
            expected_manifest_sha256=manifest_digest,
            repo_root=tmp_path,
        )


def test_local_inventory_diagnostics_and_order_are_deterministic(tmp_path, monkeypatch):
    pytest.importorskip("pyproj")
    raw_dir = tmp_path / "data/raw/emit"
    raw_dir.mkdir(parents=True)
    for native_id, stamp, rate in (
        ("CH4_PlumeComplex-42", "20241023T083741", 300.0),
        ("CH4_PlumeComplex-43", "20241023T083842", "NA"),
    ):
        metadata_path = raw_dir / f"EMIT_L2B_CH4PLMMETA_002_{stamp}_{native_id[-2:]}.json"
        properties = {
            "UTC Time Observed": stamp[:8] + "T" + stamp[9:] + "Z",
            "Latitude of max concentration": 32.25,
            "Longitude of max concentration": -103.5,
            "Emissions Rate Estimate (kg/hr)": rate,
            "Emissions Rate Estimate Uncertainty (kg/hr)": "NA",
        }
        _write_emit_document(
            metadata_path,
            [_native_emit_feature(native_id, properties)],
        )
        raster_path = raw_dir / (
            metadata_path.name.replace("CH4PLMMETA", "CH4PLM").removesuffix(".json") + ".tif"
        )
        raster_path.write_bytes(b"local TIFF placeholder checked by stubbed reader")

    monkeypatch.setattr(ingestion_inventory.shutil, "which", lambda _: "/usr/bin/tiffinfo")
    monkeypatch.setattr(
        ingestion_inventory,
        "_read_tiff",
        lambda path, executable, repo_root: {
            "path": path.relative_to(repo_root).as_posix(),
            "status": "VALID",
            "code": None,
            "message": "",
        },
    )

    first = ingestion_inventory.build_local_inventory(raw_dir, repo_root=tmp_path, tiff_workers=1)
    second = ingestion_inventory.build_local_inventory(raw_dir, repo_root=tmp_path, tiff_workers=1)

    assert first == second
    assert first["summary"]["counts"]["accepted_metadata_raster_pairs"] == 2
    assert first["summary"]["counts"]["regional_metadata_records"] == 2
    assert first["summary"]["counts"]["regional_numeric_rates"] == 1
    assert first["summary"]["counts"]["regional_null_rates"] == 1
    assert first["summary"]["accepted_rejected_diagnostics"] == []


def test_pinned_selection_is_order_independent_and_time_stratified():
    rows = [
        {
            "native_id": f"p{index:02}",
            "acquisition_time_utc": f"2024-01-{index + 1:02}T00:00:00Z",
        }
        for index in range(21)
    ]

    expected = ["p01", "p03", "p05", "p07", "p09", "p11", "p13", "p15", "p17", "p19"]
    assert [row["native_id"] for row in _stratified_ten(rows)] == expected
    assert [row["native_id"] for row in _stratified_ten(list(reversed(rows)))] == expected


def _write_pinned_dataset(tmp_path, duplicate_record=False):
    import hashlib

    raw_dir = tmp_path / "data/raw"
    manifest_dir = tmp_path / "data/manifests"
    normalized_dir = tmp_path / "data/normalized"
    raw_dir.mkdir(parents=True)
    manifest_dir.mkdir(parents=True)
    normalized_dir.mkdir(parents=True)
    metadata_path = raw_dir / "p1.json"
    raster_path = raw_dir / "p1.tif"
    metadata_path.write_text('{"provider_fixture": true}\n', encoding="utf-8")
    raster_path.write_bytes(b"test TIFF bytes")
    sha_metadata = sha256_file(metadata_path)
    now = datetime(2026, 10, 18, tzinfo=UTC)
    source = DataSource(
        provider="NASA LP DAAC",
        dataset="EMITL2BCH4PLM",
        version="002",
        url="https://doi.org/10.5067/EMIT/EMITL2BCH4PLM.002",
        license_url="https://www.usa.gov/government-works",
        citation_text="Offline pinned-loader unit fixture.",
        retrieved_at_utc=now,
        sha256=sha_metadata,
    )
    plume = PlumeObservation(
        id="NASA LP DAAC:p1",
        provider="NASA LP DAAC",
        native_id="p1",
        dataset_version="002",
        acquisition_time_utc=now,
        lon=-103.5,
        lat=32.25,
        geometry_geojson={"type": "Point", "coordinates": [-103.5, 32.25]},
        acquisition_id=None,
        emission_rate_kg_h=None,
        emission_rate_uncertainty_kg_h=None,
        uncertainty_kind=UncertaintyKind.UNKNOWN,
        missing_rate_reason=MissingReason.CRITERIA_NOT_MET,
        raw_properties={"Emissions Rate Estimate (kg/hr)": "NA"},
        source=source,
    )
    records = [plume.model_dump(mode="json")]
    if duplicate_record:
        records.append(records[0])
    normalized_bytes = (json.dumps(records, sort_keys=True, indent=2) + "\n").encode("utf-8")
    normalized_path = normalized_dir / "emit_permian_plumes.json"
    normalized_path.write_bytes(normalized_bytes)
    raw_files = [
        {
            "path": "data/raw/p1.json",
            "sha256": sha_metadata,
            "size_bytes": metadata_path.stat().st_size,
            "role": "metadata",
            "native_id": "p1",
        },
        {
            "path": "data/raw/p1.tif",
            "sha256": sha256_file(raster_path),
            "size_bytes": raster_path.stat().st_size,
            "role": "raster",
            "native_id": "p1",
        },
    ]
    manifest = {
        "schema_version": 1,
        "dataset_id": "emit-l2b-ch4plm-002-permian-v1",
        "provider": "NASA LP DAAC",
        "dataset": "EMITL2BCH4PLM",
        "version": "002",
        "raw_files": raw_files,
        "normalized": {
            "path": "data/normalized/emit_permian_plumes.json",
            "sha256": hashlib.sha256(normalized_bytes).hexdigest(),
            "size_bytes": len(normalized_bytes),
            "record_count": len(records),
        },
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")
    manifest_path = manifest_dir / "emit_permian.json"
    manifest_path.write_bytes(manifest_bytes)
    return "data/manifests/emit_permian.json", hashlib.sha256(manifest_bytes).hexdigest()


def _rewrite_manifest(tmp_path, manifest_path, update):
    manifest_file = tmp_path / manifest_path
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    update(manifest)
    manifest_file.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
