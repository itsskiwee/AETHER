# Pinned Earth orientation

`finals2000A.all` is the IERS Bulletin A Earth-orientation table used by the independent
Astropy checker. It was retrieved from the [official IERS data center](https://datacenter.iers.org/products/eop/rapid/standard/finals2000A.all).
`manifest.json` records its source, retrieval time, byte size, and SHA-256. Runtime downloads and
unpinned substitutions are disabled.

Orbit generation and independent checking must use this exact file and hash. If the pin changes,
update the manifest and record the new hash in the reproducibility bundle; do not silently refresh
the file during a run.
