"""Provenance-preserving adapters for real methane plume products.

This package is the only code allowed to construct ``PlumeObservation`` and real ``Acquisition``
records. Adapters are deliberately offline: callers fetch files through an explicitly authorized
mechanism, then pass the pinned local bytes and their ``DataSource`` provenance here.

Public API
----------
``parse_emit_plume_geojson(path, source)``
    Parse EMIT L2B CH4 plume-complex GeoJSON. The product's enhancement (ppm m) and enhancement
    uncertainty are not source emission rates. They remain verbatim in ``raw_properties``.
``parse_carbon_mapper_geojson(path, source)``
    Parse Carbon Mapper plume GeoJSON/API FeatureCollections. ``emission_auto`` and
    ``emission_uncertainty_auto`` are accepted only with the documented kg/hr meaning.
``sha256_file(path)``, ``build_manifest(...)``, ``plumes_in_region(...)``,
``cluster_to_sources(plumes, min_separation_m)``

Malformed features produce row-level diagnostics and are excluded. No missing plume record is
interpreted as a non-detection or as an acquisition. Every accepted feature retains its original
property mapping and source record; null rates retain an explicit ``MissingReason``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from aether.config import RegionConfig
from aether.contracts.enums import MissingReason, UncertaintyKind
from aether.contracts.models import DataSource, PlumeObservation, Source

ADAPTER_VERSION = "aether-ingestion/0.1.0"
TRANSFORMATION_VERSION = "aether-geojson-normalization/1"
try:
    from pyproj import Geod
except ImportError:  # pragma: no cover - availability depends on the optional geo extra
    Geod = None
_WGS84_GEOD = Geod(ellps="WGS84") if Geod is not None else None


@dataclass(frozen=True)
class IngestDiagnostic:
    """One actionable, feature-scoped ingestion diagnostic."""

    row: int | None
    feature_id: str | None
    code: str
    message: str


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 digest of the exact bytes at ``path``."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_manifest(
    paths: Iterable[str | Path],
    provider: str,
    dataset: str,
    version: str,
    citation: str,
    retrieved_at_utc: datetime,
    *,
    license_url: str | None = None,
    terms_version: str | None = None,
    terms_reviewed_for_use: bool | None = None,
) -> dict[str, Any]:
    """Build deterministic file provenance; retrieval time is supplied by the caller."""
    retrieved = _as_utc(retrieved_at_utc)
    records = []
    for value in sorted((Path(p) for p in paths), key=lambda p: p.as_posix()):
        records.append(
            {
                "path": value.as_posix(),
                "sha256": sha256_file(value),
                "size_bytes": value.stat().st_size,
            }
        )
    return {
        "provider": provider,
        "dataset": dataset,
        "version": version,
        "citation_text": citation,
        "license_url": license_url,
        "terms_version": terms_version,
        "terms_reviewed_for_use": terms_reviewed_for_use,
        "retrieved_at_utc": retrieved.isoformat().replace("+00:00", "Z"),
        "adapter_version": ADAPTER_VERSION,
        "transformation_version": TRANSFORMATION_VERSION,
        "files": records,
    }


def parse_emit_plume_geojson(
    path: str | Path, source: DataSource
) -> tuple[list[PlumeObservation], list[IngestDiagnostic]]:
    """Parse NASA EMIT L2B methane plume-complex GeoJSON without treating enhancement as flux."""
    identity_problem = _check_source_identity(source, "nasa", "emitl2bch4plm")
    if identity_problem:
        return [], [identity_problem]
    if diagnostic := _verify_source_hash(path, source):
        return [], [diagnostic]
    if _is_example_only(path):
        return [], [
            IngestDiagnostic(
                None,
                None,
                "EXAMPLE_FIXTURE_NOT_REAL_DATA",
                "synthetic fixtures cannot create REAL_OBSERVATION records",
            )
        ]
    features, diagnostics = _read_features(path)
    observations: list[PlumeObservation] = []
    seen: set[str] = set()
    filename_time = _emit_time_from_filename(Path(path).name)
    for row, feature in features:
        props = feature.get("properties")
        feature_id = _identifier(feature, props)
        try:
            if not isinstance(props, dict):
                raise _RowError("INVALID_PROPERTIES", "feature properties must be an object")
            native_id = _first(props, "Plume_ID", "global_plume_identifier", "plume_id")
            if native_id is None:
                native_id = feature_id
            if native_id is None:
                raise _RowError("MISSING_ID", "no provider plume identifier or GeoJSON feature id")
            native_id = str(native_id)
            if native_id in seen:
                raise _RowError("DUPLICATE_ID", f"duplicate provider plume id {native_id!r}")

            geometry = _validate_geometry(feature.get("geometry"))
            lon, lat = _emit_location(props, geometry)
            acquired = _acquisition_time(props, filename_time)
            # EMIT CH4PLM metadata reports enhancement and its uncertainty, not kg/h flux.
            rate_value = _first(props, "emission_rate_kg_h", "emission_rate_kg_hr")
            rate = _number(rate_value)
            rate_uncertainty = _number(
                _first(props, "emission_rate_uncertainty_kg_h", "emission_rate_uncertainty_kg_hr")
            )
            _require_nonnegative(rate, "emission rate")
            _require_nonnegative(rate_uncertainty, "emission-rate uncertainty")
            uncertainty_kind = _emit_rate_uncertainty_kind(props, rate_uncertainty)
            missing_reason = _missing_rate_reason(rate_value, rate)
            row_flags = _quality_flags(props)
            observations.append(
                PlumeObservation(
                    id=f"{source.provider}:{native_id}",
                    provider=source.provider,
                    native_id=native_id,
                    dataset_version=source.version,
                    acquisition_time_utc=acquired,
                    lon=lon,
                    lat=lat,
                    geometry_geojson=geometry,
                    # A scene reference is not a linked Acquisition; retain it in raw_properties.
                    acquisition_id=None,
                    emission_rate_kg_h=rate,
                    emission_rate_uncertainty_kg_h=rate_uncertainty,
                    uncertainty_kind=uncertainty_kind,
                    missing_rate_reason=missing_reason,
                    quality_flags=row_flags,
                    raw_properties=props,
                    source=source,
                )
            )
            seen.add(native_id)
        except (ValueError, TypeError, KeyError, _RowError) as exc:
            code = exc.code if isinstance(exc, _RowError) else "INVALID_FEATURE"
            diagnostics.append(IngestDiagnostic(row, feature_id, code, str(exc)))
    return observations, diagnostics


def parse_carbon_mapper_geojson(
    path: str | Path, source: DataSource
) -> tuple[list[PlumeObservation], list[IngestDiagnostic]]:
    """Parse Carbon Mapper Data API plume FeatureCollections using provider-defined kg/hr fields."""
    identity_problem = _check_source_identity(source, "carbon mapper", None)
    if identity_problem:
        return [], [identity_problem]
    if diagnostic := _verify_source_hash(path, source):
        return [], [diagnostic]
    if _is_example_only(path):
        return [], [
            IngestDiagnostic(
                None,
                None,
                "EXAMPLE_FIXTURE_NOT_REAL_DATA",
                "synthetic fixtures cannot create REAL_OBSERVATION records",
            )
        ]
    features, diagnostics = _read_features(path)
    observations: list[PlumeObservation] = []
    seen: set[str] = set()
    for row, feature in features:
        props = feature.get("properties")
        feature_id = _identifier(feature, props)
        try:
            if not isinstance(props, dict):
                raise _RowError("INVALID_PROPERTIES", "feature properties must be an object")
            native_id = _first(props, "plume_id", "plume_name", "id") or feature_id
            if native_id is None:
                raise _RowError("MISSING_ID", "no Carbon Mapper plume_id or GeoJSON feature id")
            native_id = str(native_id)
            if native_id in seen:
                raise _RowError("DUPLICATE_ID", f"duplicate provider plume id {native_id!r}")
            gas = _first(props, "gas", "plume_gas")
            if gas is None:
                raise _RowError("MISSING_GAS", "Carbon Mapper record must identify the gas")
            if str(gas).upper() not in {"CH4", "METHANE"}:
                raise _RowError("UNSUPPORTED_GAS", "feature is not a methane plume")

            geometry = _validate_geometry(_feature_geometry(feature, props))
            lon, lat = _carbon_mapper_location(props, geometry)
            acquired = _acquisition_time(props, None)
            rate = _number(_first(props, "emission_auto"))  # documented kg/hr
            uncertainty = _number(
                _first(props, "emission_uncertainty_auto", "emission_auto_uncertainty")
            )  # documented ± kg/hr
            _require_nonnegative(rate, "emission rate")
            _require_nonnegative(uncertainty, "emission-rate uncertainty")
            uncertainty_kind = (
                UncertaintyKind.UNKNOWN if uncertainty is None else UncertaintyKind.INTERVAL
            )
            missing_reason = _missing_rate_reason(_first(props, "emission_auto"), rate)
            observations.append(
                PlumeObservation(
                    id=f"{source.provider}:{native_id}",
                    provider=source.provider,
                    native_id=native_id,
                    dataset_version=source.version,
                    acquisition_time_utc=acquired,
                    lon=lon,
                    lat=lat,
                    geometry_geojson=geometry,
                    # Scene IDs remain metadata until a matching Acquisition is ingested.
                    acquisition_id=None,
                    emission_rate_kg_h=rate,
                    emission_rate_uncertainty_kg_h=uncertainty,
                    uncertainty_kind=uncertainty_kind,
                    missing_rate_reason=missing_reason,
                    quality_flags=_quality_flags(props),
                    raw_properties=props,
                    source=source,
                )
            )
            seen.add(native_id)
        except (ValueError, TypeError, KeyError, _RowError) as exc:
            code = exc.code if isinstance(exc, _RowError) else "INVALID_FEATURE"
            diagnostics.append(IngestDiagnostic(row, feature_id, code, str(exc)))
    return observations, diagnostics


def plumes_in_region(
    plumes: Iterable[PlumeObservation], region: RegionConfig
) -> list[PlumeObservation]:
    """Return centroid locations inside the configured WGS84 bounding box."""
    lon_min, lat_min, lon_max, lat_max = region.bbox_wgs84
    return [
        plume
        for plume in plumes
        if lon_min <= plume.lon <= lon_max and lat_min <= plume.lat <= lat_max
    ]


def cluster_to_sources(
    plumes: Iterable[PlumeObservation], min_separation_m: float
) -> list[Source]:
    """Deterministically group nearby plume centroids into unattributed source hypotheses.

    Connected components are used: every pair joined by a chain of distances at or below the
    caller-supplied threshold belongs to one hypothesis. The centroid is computed on the sphere.
    The earliest observation (then native id) supplies ``seeded_from_plume_id``.
    """
    if not math.isfinite(min_separation_m) or min_separation_m < 0:
        raise ValueError("min_separation_m must be finite and non-negative")
    ordered = sorted(plumes, key=lambda p: (p.acquisition_time_utc, p.id))
    count = len(ordered)
    parent = list(range(count))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[max(root_left, root_right)] = min(root_left, root_right)

    for left in range(count):
        for right in range(left + 1, count):
            distance_m = _distance_m(
                ordered[left].lon,
                ordered[left].lat,
                ordered[right].lon,
                ordered[right].lat,
            )
            if distance_m <= min_separation_m:
                union(left, right)

    groups: dict[int, list[PlumeObservation]] = {}
    for index, plume in enumerate(ordered):
        groups.setdefault(find(index), []).append(plume)

    result = []
    for members in sorted(groups.values(), key=lambda group: group[0].id):
        digest = hashlib.sha256("\0".join(sorted(p.id for p in members)).encode()).hexdigest()[:16]
        lon, lat = _spherical_centroid(members)
        result.append(
            Source(
                id=f"source-{digest}",
                lon=lon,
                lat=lat,
                seeded_from_plume_id=members[0].id,
                attribution_status="UNATTRIBUTED",
            )
        )
    return result


class _RowError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _read_features(
    path: str | Path,
) -> tuple[list[tuple[int, dict[str, Any]]], list[IngestDiagnostic]]:
    diagnostics: list[IngestDiagnostic] = []
    try:
        with Path(path).open(encoding="utf-8") as stream:
            document = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [], [IngestDiagnostic(None, None, "INVALID_DOCUMENT", str(exc))]
    if isinstance(document, list):
        features = [_as_feature(record) for record in document]
    elif isinstance(document, dict) and document.get("type") == "FeatureCollection":
        crs = document.get("crs")
        if crs is not None and not _is_wgs84_crs(crs):
            return [], [
                IngestDiagnostic(
                    None, None, "UNSUPPORTED_CRS", "GeoJSON CRS must be WGS84 / EPSG:4326"
                )
            ]
        features = document.get("features")
    elif isinstance(document, dict) and isinstance(
        document.get("results", document.get("data")), list
    ):
        records = document.get("results", document.get("data"))
        features = [_as_feature(record) for record in records]
    else:
        return [], [
            IngestDiagnostic(
                None,
                None,
                "INVALID_DOCUMENT",
                "expected GeoJSON FeatureCollection or Carbon Mapper records",
            )
        ]
    if not isinstance(features, list):
        return [], [
            IngestDiagnostic(None, None, "INVALID_DOCUMENT", "features must be an array")
        ]
    valid_features = []
    for row, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            diagnostics.append(
                IngestDiagnostic(row, None, "INVALID_FEATURE", "entry is not a GeoJSON Feature")
            )
        else:
            valid_features.append((row, feature))
    return valid_features, diagnostics


def _verify_source_hash(path: str | Path, source: DataSource) -> IngestDiagnostic | None:
    try:
        actual = sha256_file(path)
    except OSError as exc:
        return IngestDiagnostic(None, None, "SOURCE_UNAVAILABLE", str(exc))
    if actual != source.sha256:
        return IngestDiagnostic(
            None,
            None,
            "SOURCE_HASH_MISMATCH",
            "DataSource SHA-256 does not match input bytes",
        )
    return None


def _check_source_identity(
    source: DataSource, provider_token: str, dataset_token: str | None
) -> IngestDiagnostic | None:
    provider = source.provider.casefold()
    dataset = source.dataset.casefold()
    if provider_token not in provider or (dataset_token and dataset_token not in dataset):
        return IngestDiagnostic(
            None,
            None,
            "SOURCE_IDENTITY_MISMATCH",
            "DataSource provider or dataset does not match this adapter",
        )
    return None


def _is_example_only(path: str | Path) -> bool:
    try:
        with Path(path).open(encoding="utf-8") as stream:
            document = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    metadata = document.get("metadata") if isinstance(document, dict) else None
    if not isinstance(metadata, dict):
        return False
    return metadata.get("synthetic") is True or str(
        metadata.get("fixture_status", "")
    ).startswith("EXAMPLE_ONLY")


def _as_feature(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    if record.get("type") == "Feature":
        return record
    props = record.get("properties")
    if not isinstance(props, dict):
        props = record
    geometry = record.get("geometry", record.get("geometry_json", record.get("geometry_geojson")))
    return {
        "type": "Feature",
        "id": record.get("id", props.get("plume_id")),
        "geometry": geometry,
        "properties": props,
    }


def _is_wgs84_crs(crs: Any) -> bool:
    try:
        name = str(crs["properties"]["name"]).upper()
    except (TypeError, KeyError):
        return False
    return any(token in name for token in ("EPSG:4326", "CRS84", "CRS:84"))


def _validate_geometry(value: Any) -> dict[str, Any]:
    supported_types = {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
    }
    if not isinstance(value, dict) or value.get("type") not in supported_types:
        raise _RowError(
            "INVALID_GEOMETRY", "geometry must be a supported non-null GeoJSON geometry"
        )
    kind, coords = value["type"], value.get("coordinates")
    if coords is None:
        raise _RowError("INVALID_GEOMETRY", "geometry has no coordinates")
    positions = list(_positions(coords, kind))
    if not positions:
        raise _RowError("INVALID_GEOMETRY", "geometry has no coordinate positions")
    for position in positions:
        if len(position) < 2:
            raise _RowError(
                "INVALID_GEOMETRY", "coordinate position must contain longitude and latitude"
            )
        lon, lat = position[:2]
        if (
            not math.isfinite(lon)
            or not math.isfinite(lat)
            or not (-180 <= lon <= 180 and -90 <= lat <= 90)
        ):
            raise _RowError(
                "INVALID_GEOMETRY",
                "coordinate outside finite WGS84 longitude/latitude range",
            )
    if kind == "Polygon":
        _validate_rings(coords)
    elif kind == "MultiPolygon":
        if not coords:
            raise _RowError("INVALID_GEOMETRY", "multipolygon has no polygons")
        for polygon in coords:
            _validate_rings(polygon)
    return value


def _feature_geometry(
    feature: Mapping[str, Any], props: Mapping[str, Any]
) -> dict[str, Any]:
    geometry = feature.get("geometry")
    if geometry is not None:
        return geometry
    lon = _number(_first(props, "plume_longitude", "longitude", "lon"))
    lat = _number(_first(props, "plume_latitude", "latitude", "lat"))
    if lon is None or lat is None:
        raise _RowError(
            "MISSING_GEOMETRY",
            "geometry or a complete provider longitude/latitude pair is required",
        )
    return {"type": "Point", "coordinates": [lon, lat]}


def _positions(coords: Any, kind: str):
    if kind == "Point":
        yield _position(coords)
    elif kind in {"MultiPoint", "LineString"}:
        for position in coords:
            yield _position(position)
    elif kind == "MultiLineString":
        for line in coords:
            for position in line:
                yield _position(position)
    elif kind == "Polygon":
        for ring in coords:
            for position in ring:
                yield _position(position)
    elif kind == "MultiPolygon":
        for polygon in coords:
            for ring in polygon:
                for position in ring:
                    yield _position(position)


def _position(value: Any) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise _RowError("INVALID_GEOMETRY", "invalid coordinate position")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value):
        raise _RowError("INVALID_GEOMETRY", "coordinates must be numeric JSON values")
    position = tuple(float(v) for v in value)
    if any(not math.isfinite(v) for v in position):
        raise _RowError("INVALID_GEOMETRY", "coordinates cannot contain NaN or infinity")
    return position


def _validate_rings(rings: Any) -> None:
    if not isinstance(rings, list) or not rings:
        raise _RowError("INVALID_GEOMETRY", "polygon must contain an exterior ring")
    for ring in rings:
        if (
            not isinstance(ring, list)
            or len(ring) < 4
            or _position(ring[0])[:2] != _position(ring[-1])[:2]
        ):
            raise _RowError(
                "INVALID_GEOMETRY", "polygon rings need at least four positions and must close"
            )


def _emit_location(props: Mapping[str, Any], geometry: Mapping[str, Any]) -> tuple[float, float]:
    lon = _number(_first(props, "Longitude_of_max_concentration", "longitude_of_max_concentration"))
    lat = _number(_first(props, "Latitude_of_max_concentration", "latitude_of_max_concentration"))
    if lon is not None and lat is not None:
        return lon, lat
    return _geometry_location(geometry)


def _carbon_mapper_location(
    props: Mapping[str, Any], geometry: Mapping[str, Any]
) -> tuple[float, float]:
    lon = _number(_first(props, "plume_longitude", "longitude", "lon"))
    lat = _number(_first(props, "plume_latitude", "latitude", "lat"))
    if lon is not None and lat is not None:
        return lon, lat
    return _geometry_location(geometry)


def _geometry_location(geometry: Mapping[str, Any]) -> tuple[float, float]:
    coords = list(_positions(geometry["coordinates"], geometry["type"]))
    if geometry["type"] == "Point":
        return coords[0][0], coords[0][1]
    # Deterministic spherical mean avoids treating longitude as a linear coordinate at the dateline.
    xyz = [_unit_xyz(p[0], p[1]) for p in coords]
    x, y, z = (sum(v[i] for v in xyz) for i in range(3))
    lon = math.degrees(math.atan2(y, x))
    lat = math.degrees(math.atan2(z, math.hypot(x, y)))
    return lon, lat


def _acquisition_time(props: Mapping[str, Any], filename_time: datetime | None) -> datetime:
    raw = _first(props, "acquisition_time_utc", "datetime", "timestamp", "acquisition_time")
    if raw is None:
        raw = filename_time
    if raw is None:
        raise _RowError(
            "MISSING_ACQUISITION_TIME",
            "no acquisition timestamp in feature or EMIT granule filename",
        )
    if isinstance(raw, datetime):
        parsed = raw
    elif isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise _RowError(
                "INVALID_ACQUISITION_TIME", f"invalid ISO-8601 timestamp {raw!r}"
            ) from exc
    else:
        raise _RowError("INVALID_ACQUISITION_TIME", "acquisition timestamp must be ISO-8601 text")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _RowError("NAIVE_ACQUISITION_TIME", "acquisition timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _emit_time_from_filename(name: str) -> datetime | None:
    match = re.search(r"_(\d{8}T\d{6})_", name)
    return datetime.strptime(match.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=UTC) if match else None


def _number(value: Any) -> float | None:
    if value is None or (
        isinstance(value, str)
        and value.strip().upper() in {"", "N/A", "NA", "NULL", "NONE"}
    ):
        return None
    if isinstance(value, bool):
        raise _RowError("INVALID_NUMBER", "boolean is not a scientific numeric value")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise _RowError("INVALID_NUMBER", f"not a numeric value: {value!r}") from exc
    if not math.isfinite(result):
        raise _RowError("INVALID_NUMBER", "NaN and infinity are not permitted")
    return result


def _missing_rate_reason(rate_value: Any, rate: float | None):
    if rate is not None:
        return None
    if rate_value is None:
        return MissingReason.NOT_PROVIDED
    if isinstance(rate_value, str) and rate_value.strip().upper() in {"N/A", "NA", "NOT AVAILABLE"}:
        return MissingReason.CRITERIA_NOT_MET
    return MissingReason.UNKNOWN


def _emit_rate_uncertainty_kind(
    props: Mapping[str, Any], uncertainty: float | None
) -> UncertaintyKind:
    if uncertainty is None:
        return UncertaintyKind.UNKNOWN
    raw_kind = _first(props, "emission_rate_uncertainty_kind")
    if raw_kind is None:
        return UncertaintyKind.UNKNOWN
    try:
        return UncertaintyKind(str(raw_kind).upper())
    except ValueError as exc:
        raise _RowError(
            "INVALID_UNCERTAINTY_KIND", f"unsupported rate uncertainty kind {raw_kind!r}"
        ) from exc


def _require_nonnegative(value: float | None, label: str) -> None:
    if value is not None and value < 0:
        raise _RowError("INVALID_NUMBER", f"{label} must be non-negative")


def _quality_flags(props: Mapping[str, Any]) -> tuple[str, ...]:
    flags = []
    for key in (
        "quality",
        "status",
        "quality_flags",
        "quality_shape",
        "quality_artifacts",
        "quality_flare",
        "quality_background",
    ):
        value = props.get(key)
        if value is None or value is False or value == "":
            continue
        if isinstance(value, (list, tuple)):
            flags.extend(f"{key}:{item}" for item in value)
        elif value is True:
            flags.append(key)
        else:
            flags.append(f"{key}:{value}")
    return tuple(flags)


def _first(mapping: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in mapping and mapping[name] is not None:
            return mapping[name]
    return None


def _identifier(feature: Mapping[str, Any], props: Any) -> str | None:
    value = feature.get("id")
    if value is None and isinstance(props, dict):
        value = _first(props, "Plume_ID", "global_plume_identifier", "plume_id", "plume_name", "id")
    return None if value is None else str(value)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("retrieved_at_utc must be timezone-aware")
    return value.astimezone(UTC)


def _distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    if _WGS84_GEOD is None:
        raise RuntimeError(
            "cluster_to_sources requires the optional geo dependencies; install aether[geo]"
        )
    return _WGS84_GEOD.inv(lon1, lat1, lon2, lat2)[2]


def _unit_xyz(lon: float, lat: float) -> tuple[float, float, float]:
    lon_r, lat_r = math.radians(lon), math.radians(lat)
    return math.cos(lat_r) * math.cos(lon_r), math.cos(lat_r) * math.sin(lon_r), math.sin(lat_r)


def _spherical_centroid(plumes: list[PlumeObservation]) -> tuple[float, float]:
    xyz = [_unit_xyz(plume.lon, plume.lat) for plume in plumes]
    x, y, z = (sum(v[i] for v in xyz) for i in range(3))
    return math.degrees(math.atan2(y, x)), math.degrees(math.atan2(z, math.hypot(x, y)))


__all__ = [
    "ADAPTER_VERSION",
    "TRANSFORMATION_VERSION",
    "IngestDiagnostic",
    "build_manifest",
    "cluster_to_sources",
    "parse_carbon_mapper_geojson",
    "parse_emit_plume_geojson",
    "plumes_in_region",
    "sha256_file",
]
