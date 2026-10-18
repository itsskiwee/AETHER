# Ingestion adapters and field semantics

## Shared guarantees

The adapters read local files or saved API responses; they do not download upstream data or
create acquisition records from plume records. Adapter identity checks reject mismatched providers
or products, and fixture metadata marked synthetic is refused before it can produce a
`REAL_OBSERVATION`. The caller must construct a `DataSource` with the
actual file SHA-256, retrieval time, provider URL, version, citation and license URL. The manifest
also records the Carbon Mapper terms version and whether they were reviewed for the intended use.
Both parsers check the supplied hash against the input bytes before accepting features.

GeoJSON is interpreted as WGS84 longitude/latitude. An explicit non-WGS84 CRS is rejected.
Features with invalid geometry, time, numeric values, or duplicate native IDs are excluded with
an `IngestDiagnostic`. Original properties are retained verbatim. Missing rates stay null with a
closed `MissingReason`; no row absence becomes a valid non-detection. Scene IDs remain raw
properties and do not populate `acquisition_id` without a matching real `Acquisition` record.

## NASA EMIT L2BCH4PLM

| Provider field | Normalized field | Treatment |
|---|---|---|
| `Plume_ID` / `global_plume_identifier` | `native_id` | Provider plume-complex identity. |
| `Latitude_of_max_concentration`, `Longitude_of_max_concentration` | `lat`, `lon` | Representative maximum-enhancement location; polygon geometry is preserved separately. |
| `datetime` / `timestamp`, or granule filename timestamp | `acquisition_time_utc` | Timezone required in properties; official filename timestamp is treated as UTC. |
| `Concentration_Uncertainty` | `raw_properties` | Enhancement uncertainty. Not an emission-rate uncertainty. |
| `emission_rate_kg_h` / `emission_rate_kg_hr`, if present in an explicitly extended input | `emission_rate_kg_h` | Accepted only because the field itself explicitly declares the rate unit. A missing `N/A` value is `CRITERIA_NOT_MET`. |
| `emission_rate_uncertainty_kind`, if present | `uncertainty_kind` | Must explicitly identify `STDDEV`, `INTERVAL`, or `UNKNOWN`; otherwise the kind remains `UNKNOWN`. |

The EMIT V002 product guide describes methane enhancement in ppm·m and enhancement uncertainty;
it does not make these values interchangeable with kg/h emissions. Therefore the normal V002
metadata produces a null emission rate with `NOT_PROVIDED`, while all enhancement data remain in
the raw property map. The optional explicitly unit-named rate fields above are for input packages
that add separate rate estimates; they are not claimed to be native EMIT V002 fields.

## Carbon Mapper plume data

The parser accepts GeoJSON FeatureCollections, lists of GeoJSON features, and saved API records
under `results` or `data`. For API records without a geometry object, a Point geometry is created
only when both provider longitude and latitude fields are present.

| Provider field | Normalized field | Treatment |
|---|---|---|
| `plume_id` / `plume_name` | `native_id` | Provider plume identity. |
| `plume_gas` / `gas` | filter | Only CH4/methane records are included. Missing gas is diagnosed. |
| `datetime` | `acquisition_time_utc` | Must include an explicit timezone. |
| `plume_longitude`, `plume_latitude` | `lon`, `lat` | Provider plume location; geometry is preserved independently. |
| `emission_auto` | `emission_rate_kg_h` | Documented by Carbon Mapper in kg/hr; numerically identical to kg/h. |
| `emission_uncertainty_auto` | `emission_rate_uncertainty_kg_h` | ± kg/hr range, represented as `UncertaintyKind.INTERVAL`. |
| `quality`, `status`, `quality_*` | `quality_flags` | Values are encoded as named flags; originals remain in `raw_properties`. |

Carbon Mapper terms and API access conditions are recorded in [DATA_LICENSES.md](../DATA_LICENSES.md).
No Carbon Mapper records are currently pinned in this repository. A real-data import must capture
the exact API response/file, source URL, retrieval timestamp, terms version and SHA-256 first.

## Source clustering

`cluster_to_sources` uses the configured caller-supplied minimum distance and WGS84 ellipsoidal
geodesic distance (`pyproj.Geod`). Connected components make grouping deterministic and transitively
consistent. Generated sources remain `UNATTRIBUTED`; the earliest plume in each group is retained
as `seeded_from_plume_id`. This is a spatial grouping heuristic, not a facility attribution method.

## Reproducible scenario source construction

`build_sources(cfg, plumes=(), seed=None)` is the public runner entry point. It filters supplied
real plume records to `cfg.region`, clusters them at `cfg.sources.min_separation_m`, then fills to
`cfg.sources.count` with longitude/latitude samples inside the configured region bounds. Fill
candidates violating the minimum WGS84 geodesic separation are rejected. The fill stream is keyed
by the run seed in the `placement` RNG namespace; omitting the seed uses `cfg.random_seed`.

When no real source observations are supplied, the result is wholly synthetic and every generated
source has `UNATTRIBUTED` status and no seeded plume ID. The synthetic EMIT-shaped fixture is
deliberately refused by the real-data parser and is never used as provider observations.
