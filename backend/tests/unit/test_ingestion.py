import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from aether.contracts.enums import MissingReason, UncertaintyKind
from aether.contracts.models import DataSource
from aether.ingestion import (
    _emit_rate_uncertainty_kind,
    _missing_rate_reason,
    cluster_to_sources,
    parse_emit_plume_geojson,
    sha256_file,
)


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
