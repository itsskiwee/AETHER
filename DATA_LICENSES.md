# Data use and redistribution record

This file records the handling rules for data accepted by AETHER's ingestion adapters. The
record attached to each imported file (`DataSource` plus its manifest entry) remains authoritative
for the exact provider, product version, URL, retrieval time, citation and byte hash.

| Source | Intended use | Terms and handling |
|---|---|---|
| NASA EMIT L2BCH4PLM V002 | Historical real plume-complex geometry, acquisition metadata, enhancement and uncertainty. An enhancement value is not a source emission rate. | NASA Earthdata says NASA-led data are CC0 unless the specific content is marked with another restriction; check the dataset landing page and granule metadata for each import. Cite the LP DAAC product DOI/citation, and do not imply NASA endorsement. Keep source URL and SHA-256 in the manifest. |
| Carbon Mapper Data Platform / STAC | Optional real plume records and associated source products. | Carbon Mapper Terms of Use version dated 2026-01-13 limits use to non-commercial purposes and the defined public-good Purpose; attribution is required, and redistributed data or derivative products carry the same non-commercial and attribution terms. Review the terms again at retrieval time. Do not pin, redistribute, or use records until the exact terms and record access are captured in the manifest and the intended use is consistent with those terms. API access may be rate-limited and may include uncalibrated Tanager first-light data. |
| `data/fixtures/*_synthetic.geojson` | Offline parser examples only. | Fabricated test content. It is not a provider observation, is not source-verified, and is not evidence of a real plume. |

## Operational rules

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
