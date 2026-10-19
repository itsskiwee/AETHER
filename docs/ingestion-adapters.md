# Ingestion adapters and field semantics

## Shared guarantees

The adapters read local files or saved API responses; they do not download upstream data or
create acquisition records from plume records. Adapter identity checks reject mismatched providers
or products, and fixture metadata marked synthetic is refused before it can produce a
`REAL_OBSERVATION`. The caller must construct a `DataSource` with the actual file SHA-256,
provider URL, version, citation and license URL, and the authentic retrieval time when known.
Unknown retrieval time stays null in the dataset manifest; file or repository timestamps are not
substitutes. The manifest also records the Carbon Mapper terms version and whether they were
reviewed for the intended use. Both parsers check the supplied hash against the input bytes before
accepting features.

GeoJSON is interpreted as WGS84 longitude/latitude. An explicit non-WGS84 CRS is rejected.
Features with invalid geometry, time, numeric values, or duplicate native IDs are excluded with
an `IngestDiagnostic`. Original properties are retained verbatim. Missing rates stay null with a
closed `MissingReason`; no row absence becomes a valid non-detection. Scene IDs remain raw
properties and do not populate `acquisition_id` without a matching real `Acquisition` record.

## NASA EMIT L2BCH4PLM

| Provider field | Normalized field | Treatment |
|---|---|---|
| `Plume ID` (also `Plume_ID`, `global_plume_identifier`, `plume_id`) | `native_id` | Provider plume-complex identity. |
| `Latitude of max concentration`, `Longitude of max concentration` (underscore variants also accepted) | `lat`, `lon` | Representative maximum-concentration location; polygon geometry is preserved separately. |
| `UTC Time Observed` (also `datetime`, `timestamp`, `acquisition_time_utc`) | `acquisition_time_utc` | Must include an explicit timezone; normalized to UTC. |
| `Max Plume Concentration (ppm m)` | `raw_properties` | Enhancement in ppm·m, not an emission rate. Preserved verbatim. |
| `Emissions Rate Estimate (kg/hr)` | `emission_rate_kg_h` | Native V002 rate estimate. kg/hr is numerically identical to kg/h. `NA` is `None` with `CRITERIA_NOT_MET`. |
| `Emissions Rate Estimate Uncertainty (kg/hr)` | `emission_rate_uncertainty_kg_h` | Preserved as a numeric kg/h magnitude when present. `uncertainty_kind` stays `UNKNOWN` until the provider definition is reviewed; the field name alone does not establish a standard deviation or interval. |

The NASA V002 product description states that GeoJSON metadata carries plume outlines, maximum
enhancement coordinates, estimated emission rates, and their uncertainty. Estimates are `N/A`
when retrieval criteria are not met. Enhancement (ppm·m) is never substituted for the distinct
emission-rate estimate (kg/hr). The product is detection-oriented: missing plume rows are not
non-detections and historical rates do not set simulated truth or activity.

The upstream files observed locally use the spaced field names in the first column. The parser
also retains its earlier normalized aliases for compatible saved inputs. See [the NASA product
description](https://data.nasa.gov/dataset/emit-l2b-estimated-methane-plume-complexes-60-m-v002)
and the [EMIT L2B GHG User Guide](https://lpdaac.usgs.gov/documents/2250/EMIT_L2B_GHG_User_Guide_V2.pdf)
for product context. The guide describes uncertainty metadata but does not define the exact
statistical meaning of the native rate-uncertainty field used here.

## Local inventory and pinned sample

With the full local download in `data/raw/EMITL2BCH4PLM_002-20261018_042728/`, run
`python -m aether.ingestion.inventory` from `backend/`. The command hashes every metadata/TIFF file,
checks TIFF readability with `tiffinfo -D`, pairs names, applies the parser to each metadata record,
and writes stable accepted/rejected diagnostics to `data/manifests/emit_inventory.json`. It does
not fetch, rewrite, or derive fluxes from any raster. The inventory reports the configured Permian
bbox coverage and connected-component source count at 500 m.

After the shared `DataSource.retrieved_at_utc` contract permits an unknown timestamp, run
`python -m aether.ingestion.prepare_pinned`. This deterministically selects ten regional numeric
rate records and ten provider-`NA` records, copies only their original metadata/TIFF pairs, writes
normalized observations and `data/manifests/emit_permian.json`, and records the local inventory
hash plus available provenance. The normalized records keep the provider's native rate uncertainty
with `uncertainty_kind: UNKNOWN`. The manifest's null retrieval time and empty exact-file URL list
are intentional provenance gaps.

Runners load that fixed input with
`load_pinned_plume_dataset(manifest_path, expected_manifest_sha256=..., repo_root=...)`. The loader
checks the manifest and normalized hashes, source identity, metadata/raster pair completeness, and
raw file hashes without network access or directory scanning.

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
