# Data use and redistribution record

This file records the handling rules for data accepted by AETHER's ingestion adapters. The
record attached to each imported file (`DataSource` plus its manifest entry) remains authoritative
for the exact provider, product version, URL, retrieval time, citation and byte hash.

| Source | Intended use | Terms and handling |
|---|---|---|
| NASA EMIT L2BCH4PLM V002 | Historical real plume-complex geometry, acquisition metadata, enhancement, and provider emission estimates when available. Enhancement is not a source emission rate. | The NASA Open Data product page links the US Government Works policy (`https://www.usa.gov/government-works`). Preserve NASA/LP DAAC attribution, the DOI citation, and each selected input's SHA-256. This repository records no exact retrieval timestamp or per-file download URL where that evidence is unavailable; it does not infer them from filenames or filesystem metadata. The version-controlled tree excludes the bulk download; the original local files remain ignored. This task intends to retain only the pinned representative sample. An earlier Git revision contains the bulk files; this task removes them from the current tree without rewriting that history. |
| Carbon Mapper Data Platform / STAC (P1, out of P0) | Optional adapter only. No Carbon Mapper records or fixtures are stored. | A previously reviewed Terms of Use copy was dated 2026-01-13, but that does not authorize a specific import. Before storing any record, re-check and record the current terms, retrieval details, and intended-use compatibility in its manifest. Attribution is required; redistribution may carry non-commercial restrictions. API access may be rate-limited and may include uncalibrated Tanager first-light data. |
| `data/fixtures/*_synthetic.geojson` | Offline parser examples only. | Fabricated test content. It is not a provider observation, is not source-verified, and is not evidence of a real plume. |

## Operational rules

### User-requested current-data context (18 October 2026)

The optional satellite-context view reads public CelesTrak GP JSON and NASA CMR
discovery metadata. These inputs are stored locally under ignored `data/live_context/`,
with original response hashes, exact request URLs and authentic retrieval times. No
Carbon Mapper data, authenticated response or NASA raster is downloaded by this view.
The app's MIT code license does not assert a new license over provider data.

- CelesTrak attribution: CelesTrak / T. S. Kelso, GP orbital elements, JSON OMM-compatible
  format. Documentation: https://celestrak.org/NORAD/documentation/gp-data-formats.php.
  Usage policy reviewed 18 October 2026: https://celestrak.org/usage-policy.php (updated
  22 May 2026). GP updates are every two hours; cache server-side, fetch only the needed
  group, and stop after any non-200 HTTP response. The updater implements that cadence
  and stops on errors. Provider snapshots are not added to the public source tree.
- NASA CMR attribution: NASA EOSDIS Common Metadata Repository; EMITL2BCH4PLM V002
  discovery metadata. API: https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html.
  Data-use guidance: https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy.
  Discovery metadata are not methane measurements. Observation times remain separate
  from catalogue modification and retrieval times. Protected granule download links do
  not imply credentials or download authorization are available to the app.

- Never commit credentials, access tokens, or authenticated request headers.
- Store real downloaded source files under `data/raw/` only when the source's current terms permit it; this directory is ignored by git.
- A manifest's `license_url` may be null when the product terms are not explicit. Do not replace an unknown license with an assumed one.
- Preserve provider properties and field meanings. Do not convert enhancement concentration into mass flux. Normalize a rate only when the source field explicitly identifies a rate and its unit.
- Do not derive a valid non-detection or an acquisition from the absence of a plume feature.

## References

- NASA Earthdata data use and citation guidance: <https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy>
- NASA LP DAAC EMIT L2BCH4PLM V002: <https://doi.org/10.5067/EMIT/EMITL2BCH4PLM.002>
- Carbon Mapper Terms of Use: <https://carbonmapper.org/terms>
- Carbon Mapper Data API docs: <https://api.carbonmapper.org/api/v1/docs>
