from datetime import UTC, datetime
from types import SimpleNamespace

from pyproj import Geod

from aether.config import load_scenario
from aether.ingestion import build_sources


def test_uniform_source_construction_is_keyed_and_region_bounded(base_config_path):
    cfg = load_scenario(base_config_path).model
    first = build_sources(cfg, seed=721)
    second = build_sources(cfg, seed=721)
    assert [source.model_dump(mode="json") for source in first] == [
        source.model_dump(mode="json") for source in second
    ]
    assert len(first) == cfg.sources.count
    lon_min, lat_min, lon_max, lat_max = cfg.region.bbox_wgs84
    assert all(lon_min <= source.lon <= lon_max for source in first)
    assert all(lat_min <= source.lat <= lat_max for source in first)

    geod = Geod(ellps="WGS84")
    for i, left in enumerate(first):
        for right in first[i + 1 :]:
            assert geod.inv(left.lon, left.lat, right.lon, right.lat)[2] >= (
                cfg.sources.min_separation_m
            )


def test_plume_clusters_are_preserved_and_uniformly_filled(base_config_path):
    cfg = load_scenario(base_config_path).model
    observed_at = datetime(2026, 10, 17, tzinfo=UTC)
    plumes = [
        SimpleNamespace(id="p1", acquisition_time_utc=observed_at, lon=-103.0, lat=32.0),
        SimpleNamespace(id="p2", acquisition_time_utc=observed_at, lon=-102.999, lat=32.0),
        SimpleNamespace(id="p3", acquisition_time_utc=observed_at, lon=-101.5, lat=33.0),
        SimpleNamespace(id="outside", acquisition_time_utc=observed_at, lon=-90.0, lat=32.0),
    ]

    sources = build_sources(cfg, plumes, seed=123)

    assert len(sources) == cfg.sources.count
    assert {source.seeded_from_plume_id for source in sources if source.seeded_from_plume_id} == {
        "p1",
        "p3",
    }
    assert all(source.attribution_status == "UNATTRIBUTED" for source in sources)
    assert all(source.seeded_from_plume_id != "outside" for source in sources)
