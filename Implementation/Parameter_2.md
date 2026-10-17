# AETHER — Parameter Set 2: Gap Review and Expanded Parameters

**Companion to:** `AETHER_Product_Requirements_Document.md` (PRD v1.0) and `Parameter_1.md` (source concept [C00])
**Prepared:** 17 October 2026 · **Status:** Proposed parameters; nothing here is implemented or measured

> Same evidence legend as the PRD: **[D]** design decision, **[A]** assumption that needs sensitivity testing, **[T]** target to be tested. Every default below is a *starting value to put in config*, not a validated number. Anything marked "verify" is a standard or tool that should be checked against its current version before you cite it.

---

## Part A — Review: what the PRD is missing

The PRD is strong on scientific integrity: provenance classes, non-detection semantics, fair baselines and claim discipline are all handled well. Its gaps sit in the layers around that core, where most hackathon projects break: concrete numbers, security, API mechanics, determinism, and the interface.

### A.1 Gaps that would break a P0 requirement

| # | Gap | Where in PRD | Why it matters | Fix (this doc) |
|---|---|---|---|---|
| G-01 | **CP-SAT is not deterministic with parallel workers or wall-clock limits.** FR-SIM-002 demands an identical decision trace, but `solver_timeout_seconds: 20` plus multi-threaded search can return different schedules on reruns. | §7.4, §8.3 FR-SIM-002, §11.4 | T-EVAL-02 (same-seed replay) will fail intermittently. | ENG-OPT-001…004 |
| G-02 | **Hidden-truth isolation relies on DB grants, but P0 runs in-process (CLI, SQLite fallback).** A Postgres role does nothing if the planner and the simulator share one Python process and memory. | §10.1, §10.4 "in-process CLI", §11.5 | The most important scientific invariant has no P0 enforcement. | SEC-ISO-001…005 |
| G-03 | **Astropy downloads IERS Earth-orientation tables at runtime.** Offline demo (NFR-008) either fails or silently falls back to degraded precision. | §5.1, NFR-004, NFR-008 | Orbit results change between online and offline runs, so reproducibility breaks. | ENG-ORB-009 |
| G-04 | **No canonical form for hashing.** `config_hash` and `payload_hash` are SHA-256 of *what*? Reformatting YAML changes the hash. | §10.3, §11.1 | Replay mismatch errors with no real cause. | ENG-REP-001 |
| G-05 | **RNG algorithm and stream-keying unspecified.** §8.2 asks for keyed streams by `(scenario, target, sensor, time)` but doesn't say how. | §8.2 step 5 | Common-random-number design can't be implemented consistently. | ENG-REP-002…003 |
| G-06 | **"Arrival order" baseline (B1) has no request generator.** Nothing in the PRD creates "requests". | §7.5 | B1 can't be implemented fairly. | ENG-SIM-006 |
| G-07 | **The decision-explanation response (§12.3) has no endpoint.** | §12 table | Screen E has nothing to call. | API-EP list |
| G-08 | **No authentication or authorization design.** "Auth for mutations" appears once (NFR-010). There are no roles, tokens, sessions or scopes. | §12, NFR-010 | Nobody can implement "server-side authorization" from that line. | SEC-AUTH, SEC-RBAC |
| G-09 | **Almost every physical/operational parameter is qualitative.** Pass-search step, elevation/off-nadir limits, slew, battery, storage, solar zenith, stale-TLE age, POD curve, freeze window and so on have no values. | §5.2, §5.3, §6, §20 | Every engineer picks a different number; benchmarks are not comparable. | Part C |
| G-10 | **"Within floating precision" undefined.** | T-EVAL-02 | Tests can't assert it. | ENG-REP-005 |

### A.2 Gaps that weaken the project

**Security / cybersecurity**
- The threat model (§15.1) is a list of nouns with no trust-boundary analysis (STRIDE), attacker profiles, or severity.
- Nothing on: GDAL driver attack surface, XML (OMM) entity attacks, YAML deserialization, zip-slip in import/export bundles, XSS from provider metadata, security headers/CSP, CORS, session handling, supply-chain pinning, CI hardening, container hardening, backups, log redaction, vulnerability disclosure (`SECURITY.md`).
- The audit log is "append-only" but not tamper-evident.
- There's no guard to stop real command/uplink code from ever entering the repo, which matters because the product's credibility depends on "we do not command spacecraft".
- No dual-use / misuse analysis (for example, someone using the tool to harass a facility operator) and no correction/right-of-reply process.

**Engineering**
- No DEM/terrain occlusion spec, even though "terrain" appears in §5.2.
- No surface albedo, sun-glint or viewing-zenith effect on detectability, though SWIR methane retrievals depend heavily on these.
- Cloud model has no spatial/temporal correlation; independent per-pass cloud draws make weather unrealistically forgiving.
- Area sources vs point targets: there's no footprint-coverage-fraction rule.
- Units library not chosen ("typed quantities" with no `pint`/`astropy.units` decision).
- Schema/config versioning and DB migrations are absent.
- No environments (dev/staging/demo), deployment target, backup or cost plan.

**API**
- Pagination, filtering, sorting, bbox/time syntax, max page size, request size limits, rate-limit headers, ETags/caching, deprecation policy, SSE resume semantics, and NaN/null rules are missing.
- The custom error envelope could follow RFC 9457 Problem Details instead of inventing one.
- Missing endpoints: list runs, cancel run, list/get scenarios, get single source, explanations, citations/methodology, evaluator-only truth access.
- The event stream lacks `NOT_OBSERVED`, `PLAN_REJECTED`, `RUN_FAILED`, `RUN_CANCELLED` and a `schema_version` field.

**UI/UX**
- §13 describes *what* each screen shows but there's no design system: no typography, spacing, color tokens, component inventory, density, motion, number formatting or copy rules.
- The provenance visual encoding is required but undefined.
- No rule linking displayed precision to uncertainty (showing `652.31 kg/h` for a ±300 estimate is a scientific-integrity bug).
- No performance budget, no usability testing, no visual-regression or automated a11y testing.
- Nothing addresses the "generic AI dashboard" look, which matters for judging (see Part F).

**Other**
- No hour-level hackathon schedule; §18.3 explicitly refuses dates.
- No RACI or decision log (ADRs).
- `README.md` says AETHER will "verify major methane emissions", which conflicts with PRD principle 7 and the claim table in §22.3. Suggest "corroborate" or "collect evidence on".
- `Parameter_1.md` still has chat paste residue ("NASA Open Data Portal +1", "AAAI +1", "dw.com" at lines 21–22, 37–38, 57, 131–132, 322, 329, 386). Clean these before anyone external reads it.
- Explanation API example lacks `schema_version`, `run_id`, and `evidence_ids`, which NFR-013 requires.

---

## Part B — How to use these parameters

1. Every parameter gets one row in a machine-readable registry: `configs/parameters.yaml` with `id, value, unit, range, tag, rationale, owner`.
2. Pydantic loads the registry. Out-of-range values fail at `POST /scenarios/validate`, with no silent clamping.
3. Every run bundle exports the resolved parameter set and its canonical hash (ENG-REP-001).
4. Parameters tagged **[A]** must appear in at least one sensitivity sweep before research v1 (FR-SIM-009).

```yaml
# configs/parameters.yaml (shape)
- id: ENG-ORB-001
  name: pass_search_coarse_step
  value: 10
  unit: s
  range: [1, 30]
  tag: D
  owner: orbit
  rationale: "Must be < half the minimum supported window length"
```

---

## Part C — Engineering parameters

### C.1 Orbit and geometry (`ENG-ORB`)

| ID | Parameter | Default | Range / allowed | Tag | Notes |
|---|---|---|---|---|---|
| ENG-ORB-001 | Pass-search coarse step | 10 s | 1–30 s | D | Must be < ½ × min window length, or short passes get missed (§6). |
| ENG-ORB-002 | Window boundary refine tolerance | 0.1 s | 0.01–1 s | D | Brent/bisection on sign change of the visibility function. |
| ENG-ORB-003 | Minimum usable window | exposure + settle (≈ 20 s) | derived | D | Reject sub-duration windows. |
| ENG-ORB-004 | Max off-nadir pointing | 30° | 0–45° | A | Virtual sensor; vary in sweep. |
| ENG-ORB-005 | Min target elevation (from ground) | 60° | 30–90° | A | Equivalent to an off-nadir cap; keep both consistent. |
| ENG-ORB-006 | Element age: warn | 3 days | 1–7 | A | LEO SGP4 error grows quickly with age. |
| ENG-ORB-007 | Element age: block | 14 days | 7–30 | A | `STALE_ELEMENTS` rejection. |
| ENG-ORB-008 | Frame chain | TEME → ITRS via Astropy | fixed | D | Cross-check against Skyfield in tests (§17.3). |
| ENG-ORB-009 | Earth-orientation data | pinned IERS file in `data/eop/`, `iers.conf.auto_download = False` | pinned hash | D | Fixes **G-03**. Export EOP file hash in bundle. |
| ENG-ORB-010 | Terrain model | none (ellipsoid) in P0; Copernicus GLO-30 DEM in P1 | — | D | Label "ellipsoid only" in UI when DEM is off. |
| ENG-ORB-011 | Target representation | point (P0); polygon + coverage fraction (P1) | — | D | |
| ENG-ORB-012 | Min footprint coverage fraction | 0.8 | 0.5–1.0 | A | Area sources only. |
| ENG-ORB-013 | Golden test orbits | ≥ 3 (equatorial, sun-synchronous, ISS-like 51.6°) | — | D | Plus one decayed-orbit error case. |
| ENG-ORB-014 | Geometry cross-check tolerance | ≤ 1 km position, ≤ 2 s window edge vs second library | — | T | Fails G1 gate if exceeded. |

### C.2 Virtual spacecraft and sensor (`ENG-SC`, `ENG-SEN`)

All values are **virtual, scenario-authored**. Never label them as EMIT or any real instrument.

| ID | Parameter | Default | Range | Tag | Notes |
|---|---|---|---|---|---|
| ENG-SC-001 | Slew rate (per axis) | 1.0 °/s | 0.2–3 °/s | A | |
| ENG-SC-002 | Settle time after slew | 10 s | 0–60 s | A | |
| ENG-SC-003 | Battery capacity | 120 Wh | 20–500 | A | |
| ENG-SC-004 | Min state of charge | 30 % | 10–60 % | A | Hard floor; schedule may never cross it. |
| ENG-SC-005 | Acquisition power draw | 60 W | 10–200 | A | |
| ENG-SC-006 | Idle power draw | 15 W | 5–50 | A | |
| ENG-SC-007 | Solar charge (sunlit) | 40 W net | 0–150 | A | P1; P0 may disable with a label. |
| ENG-SC-008 | Onboard storage | 64 GB (decimal) | 4–512 | A | Canonical bytes in API. |
| ENG-SC-009 | Data per acquisition | 2 GB | 0.1–10 | A | |
| ENG-SC-010 | Max acquisitions per orbit | 4 | 1–20 | A | Duty-cycle proxy. |
| ENG-SC-011 | Downlink model (P0) | `LATENCY_SURROGATE` fixed 3 h, labeled | `NONE` / `SURROGATE` / `STATIONS` | D | Never show a physical downlink without defined stations. |
| ENG-SEN-001 | Exposure duration | 10 s | 1–60 | A | |
| ENG-SEN-002 | Ground sampling distance | 60 m | 10–300 | A | |
| ENG-SEN-003 | Swath width | 30 km | 5–200 | A | |
| ENG-SEN-004 | Max solar zenith angle | 70° | 50–80° | A | SWIR retrieval needs sunlight. |
| ENG-SEN-005 | POD model | logistic in Q: `POD = 1/(1+exp(-k(Q−Q50)))` × validity | fixed family P0 | D | |
| ENG-SEN-006 | `Q50` (50 % detection rate) | 500 kg CH₄/h | 100–2000 | A | Main sensitivity-sweep axis. |
| ENG-SEN-007 | Logistic slope `k` | 0.006 per (kg/h) | 0.001–0.02 | A | |
| ENG-SEN-008 | POD modifiers | albedo, viewing zenith, wind | multiplicative, each in [0,1] | A | P1; P0 = 1.0 and labeled "not modeled". |
| ENG-SEN-009 | False-positive rate (inactive) | 0.01 per valid acquisition | 0–0.1 | A | |
| ENG-SEN-010 | Sun-glint exclusion | glint angle < 20° over water → invalid | 10–40° | A | P1. |
| ENG-SEN-011 | Flux measurement error | lognormal, σ_log = 0.35 | 0.1–0.8 | A | Conditional on detection. |

### C.3 Weather / validity (`ENG-WX`)

| ID | Parameter | Default | Range | Tag | Notes |
|---|---|---|---|---|---|
| ENG-WX-001 | Validity model | `P(valid) = 1 − cloud_fraction` | — | D | |
| ENG-WX-002 | Hard invalid threshold | cloud_fraction > 0.3 → `INVALID_ACQUISITION` | 0.1–0.6 | A | |
| ENG-WX-003 | Cloud temporal correlation | AR(1), φ = 0.8 per hour | 0–0.98 | A | Fixes "independent cloud per pass" unrealism. |
| ENG-WX-004 | Cloud spatial correlation length | 50 km | 0–500 | A | Gaussian random field or a simple grid kernel. |
| ENG-WX-005 | Forecast error model | `forecast = truth + N(0, σ)` clipped, σ grows 0.05/24 h | — | A | Planner sees the forecast; simulator samples the truth. |
| ENG-WX-006 | ERA5 future-use guard | reject `valid_time > now` for `kind=reanalysis` | fixed | D | §16. |

### C.4 Belief model (`ENG-BEL`)

| ID | Parameter | Default | Range | Tag | Notes |
|---|---|---|---|---|---|
| ENG-BEL-001 | HMM time step | 1 h | 0.25–6 h | D | |
| ENG-BEL-002 | Persistence `P(1→1)` | 0.97 /h | 0.8–0.999 | A | Already in §11.4. |
| ENG-BEL-003 | Reactivation `P(0→1)` | 0.03 /h | 0.001–0.2 | A | |
| ENG-BEL-004 | Prior `P(active)` for new source with one detection | 0.7 | 0.3–0.95 | A | |
| ENG-BEL-005 | Rate prior | lognormal, median 400 kg/h, σ_log 1.0 | — | A | |
| ENG-BEL-006 | Rate representation | discrete grid, 200 log-spaced bins, 10–20 000 kg/h | 50–1000 bins | D | Simple, exact and testable. |
| ENG-BEL-007 | Probability clip for logs | 1e-12 | 1e-15–1e-6 | D | |
| ENG-BEL-008 | Credible interval reported | 90 % equal-tailed | 50–95 % | D | Matches §9.2 coverage metric. |
| ENG-BEL-009 | Monte Carlo samples for EIG (P1 KL) | 2000 | 500–20 000 | D | Seed recorded. |

### C.5 Optimizer (`ENG-OPT`)

| ID | Parameter | Default | Range | Tag | Notes |
|---|---|---|---|---|---|
| ENG-OPT-001 | CP-SAT `num_workers` (reproducible mode) | 1 | 1 | D | **Fixes G-01.** Benchmarks and replays use this mode. |
| ENG-OPT-002 | CP-SAT `max_deterministic_time` | 30 | 5–300 | D | Use this as the limit instead of wall-clock `max_time_in_seconds` in reproducible mode. |
| ENG-OPT-003 | CP-SAT `random_seed` | derived from scenario seed | — | D | |
| ENG-OPT-004 | Fast mode (UI exploration only) | `num_workers=8`, wall-clock 20 s | — | D | Results tagged `NON_REPRODUCIBLE_SOLVE`; never in benchmarks. |
| ENG-OPT-005 | Objective integer scale | 10 000 | 100–1e6 | D | Log rounding loss; assert no int64 overflow. |
| ENG-OPT-006 | Max candidates per solve | 5000 | 100–50 000 | D | |
| ENG-OPT-007 | Pruning: top-K windows per source | 10 | 1–100 | D | Prune fraction reported (§9.3). |
| ENG-OPT-008 | Min utility to keep candidate | > 0 after scaling | — | D | |
| ENG-OPT-009 | Freeze window | 30 min | 0–6 h | D | Tasks starting within freeze can't change. |
| ENG-OPT-010 | Max visits per source per solve | 1 (P0) | 1–5 | D | §7.2 double-count guard. |
| ENG-OPT-011 | Tie-break rule | lowest `window_id` lexicographic | fixed | D | Deterministic. |
| ENG-OPT-012 | Rolling-horizon replan triggers | `informative_acquisition`, `forecast_revision`, `resource_change` | — | D | |

### C.6 Simulation and reproducibility (`ENG-SIM`, `ENG-REP`)

| ID | Parameter | Default | Tag | Notes |
|---|---|---|---|---|
| ENG-SIM-001 | Hidden sources (P0) | 15 | D | |
| ENG-SIM-002 | Virtual spacecraft (P0) | 2 | D | |
| ENG-SIM-003 | Horizon | 72 h | D | |
| ENG-SIM-004 | Dev seeds / holdout seeds | 20 / 30 | D | Separate files, holdout locked by hash before tuning. |
| ENG-SIM-005 | Evaluation timestamps (Brier) | every 6 h | D | Same for all policies. |
| ENG-SIM-006 | Request generator for B1 | Poisson arrivals, λ = 1 request / source / 24 h, seeded | A | **Fixes G-06.** Same stream for every policy. |
| ENG-REP-001 | Canonical hashing | RFC 8785 JSON Canonicalization of parsed config → SHA-256 | D | **Fixes G-04.** Never hash raw YAML text. |
| ENG-REP-002 | RNG | NumPy `PCG64` via `SeedSequence` | D | |
| ENG-REP-003 | Keyed streams | `SeedSequence(scenario_seed, spawn_key=(hash32(target), hash32(sensor), epoch_minute))` | D | **Fixes G-05.** |
| ENG-REP-004 | Thread determinism | `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1` in reproducible mode | D | |
| ENG-REP-005 | Replay tolerance | bit-identical on same platform; cross-platform `rtol=1e-9, atol=1e-12` on posteriors; event IDs exactly equal | T | **Fixes G-10.** |
| ENG-REP-006 | Units library | `astropy.units` in orbit; `pint` elsewhere, *or* one of them everywhere | D | Decide once (ADR); ban bare floats in public schemas. |
| ENG-REP-007 | Schema versioning | `schema_version` on every config, event, export; Alembic for DB | D | |

---

## Part D — Security and cybersecurity parameters

### D.1 Threat model (STRIDE per trust boundary)

| Boundary | Main threats | Key controls |
|---|---|---|
| Upstream data → ingest | **T**ampering (poisoned GeoJSON/COG), **D**oS (geometry/decompression bombs), **I**nfo injection (prompt-like strings in metadata) | SEC-IN-*, hash pinning, provider allowlist |
| Browser → API | **S**poofing, **E**levation (write as viewer), XSS, CSRF, scraping | SEC-AUTH-*, SEC-RBAC, SEC-WEB-* |
| API → DB | SQL injection, expensive spatial queries, data exfiltration | parameterized queries, SEC-DB-* |
| Planner ↔ hidden truth | **I**nformation disclosure (truth leakage, the scientific integrity failure) | SEC-ISO-* |
| CI/CD → release | supply-chain compromise, tampered bundles | SEC-SC-* |
| Run artifacts → public | **R**epudiation (altered results), license violations | hash-chained audit, signed bundles, SEC-GOV-* |
| Humans → facility operators | reputational harm, harassment via named facilities | SEC-ABUSE-* |

Attacker profiles to design against: (1) anonymous internet user hitting a public demo, (2) authenticated researcher trying to see hidden truth or another team's runs, (3) malicious upstream file, (4) compromised dependency, (5) a well-meaning teammate committing a token.

### D.2 Authentication and sessions (`SEC-AUTH`)

| ID | Parameter | Default | Notes |
|---|---|---|---|
| SEC-AUTH-001 | Human login | OIDC Authorization Code + PKCE (e.g., GitHub/Google via an IdP) | Hackathon: allow a single shared demo login *only* in read-only mode. |
| SEC-AUTH-002 | Machine/CLI auth | scoped personal API tokens, 128-bit+ random, stored as SHA-256 hash | Show once at creation. |
| SEC-AUTH-003 | Token expiry | 90 days, revocable | |
| SEC-AUTH-004 | Session cookie | `HttpOnly; Secure; SameSite=Lax; Path=/` | |
| SEC-AUTH-005 | Session idle / absolute timeout | 30 min / 8 h | |
| SEC-AUTH-006 | CSRF | double-submit token or `SameSite` + Origin check on all cookie-auth writes | |
| SEC-AUTH-007 | Login rate limit | 10 attempts / 15 min / IP | |
| SEC-AUTH-008 | MFA | required for `data_admin`, `evaluator`, `security_admin` | Delegate to IdP. |

### D.3 Roles and permissions (`SEC-RBAC`)

| Capability | public_viewer | researcher | run_operator | data_admin | evaluator | security_admin |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Read real observations, sources, methodology | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Read own/shared runs, plans, metrics | public runs only | ✓ | ✓ | ✓ | ✓ | — |
| Validate scenarios | — | ✓ | ✓ | ✓ | ✓ | — |
| Create/cancel/replan runs | — | — | ✓ | — | ✓ | — |
| Import datasets, edit license manifest | — | — | — | ✓ | — | — |
| Read `sim_truth`, run scorer | — | — | — | — | ✓ | — |
| Manage tokens, roles, audit export | — | — | — | — | — | ✓ |

Rules: deny by default; authorization checked in the API layer **and** by DB role; no role can write a `provenance_class` other than its own (§10.1); the evaluator can't create runs on holdout seeds it hasn't locked.

### D.4 Hidden-truth isolation (`SEC-ISO`), fixes G-02

| ID | Control |
|---|---|
| SEC-ISO-001 | Truth generation and scoring run in a **separate OS process** (`aether-scorer`) with its own credentials. The planner process never holds truth in memory. |
| SEC-ISO-002 | Import contract enforced by `import-linter`: `aether.planning`, `aether.inference`, `aether.api` must not import `aether.simulation.truth` or `aether.evaluation.scorer`. CI fails on violation. |
| SEC-ISO-003 | The simulator exposes only an `observe(window) -> ObservationOutcome` interface to the loop; outcomes contain no latent state fields (checked by schema test). |
| SEC-ISO-004 | SQLite fallback: truth stored in a separate file with OS permissions `0600` owned by the scorer user; the planner's DB connection never `ATTACH`es it. |
| SEC-ISO-005 | Leakage canaries: inject a unique sentinel into truth; scan logs, API responses, exports and front-end bundles for it in CI. |
| SEC-ISO-006 | Metrics endpoints serve only **completed** evaluations; no live truth-derived metrics during a run (prevents side-channel leakage through scores). |

### D.5 Input handling (`SEC-IN`)

| ID | Parameter | Default |
|---|---|---|
| SEC-IN-001 | Max upload size | 50 MB |
| SEC-IN-002 | Max raster dimensions | 10 000 × 10 000 px, ≤ 4 bands |
| SEC-IN-003 | Allowed raster drivers | GTiff/COG only; disable all other GDAL drivers for untrusted input (verify current rasterio/GDAL option names) |
| SEC-IN-004 | GDAL network access for untrusted files | disabled; no `/vsicurl/`, `/vsizip/` on user paths; `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR` |
| SEC-IN-005 | Max vertices per feature / features per file | 10 000 / 5 000 |
| SEC-IN-006 | Archive limits | ≤ 1 000 entries, ≤ 500 MB uncompressed, ratio ≤ 100:1, reject symlinks, absolute paths and `..` (zip-slip) |
| SEC-IN-007 | YAML | `yaml.safe_load` only |
| SEC-IN-008 | XML (OMM) | `defusedxml`; no DTDs or external entities |
| SEC-IN-009 | JSON | max 5 MB body, max depth 32, reject NaN/Infinity |
| SEC-IN-010 | Serialization of artifacts | JSON/Parquet/GeoTIFF only; **never** `pickle`/`joblib` for anything that crosses a trust boundary |
| SEC-IN-011 | Outbound fetch | allowlist: Earthdata/LP DAAC, Carbon Mapper API, CelesTrak, CDS; block private IP ranges and metadata endpoints (SSRF); 10 s connect / 60 s read timeout |
| SEC-IN-012 | Metadata strings | treated as untrusted text: length-capped (4 KB), rendered as text not HTML, never fed to an LLM as instructions |
| SEC-IN-013 | Parser sandbox | run raster/vector parsing in a worker with CPU 60 s, memory 2 GB, no network |

### D.6 Web and API surface (`SEC-WEB`)

| ID | Parameter | Default |
|---|---|---|
| SEC-WEB-001 | TLS | 1.2 minimum, 1.3 preferred; HSTS `max-age=31536000; includeSubDomains` |
| SEC-WEB-002 | CSP | `default-src 'self'; img-src 'self' data: <tile hosts>; connect-src 'self' <tile hosts>; script-src 'self'; style-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'` (Cesium/MapLibre may need `worker-src blob:`, so add only what's proven necessary) |
| SEC-WEB-003 | Other headers | `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` denying camera/mic/geolocation |
| SEC-WEB-004 | CORS | exact origin allowlist; never `*` with credentials |
| SEC-WEB-005 | Rate limits | public GET 60/min/IP · authenticated 600/min/token · `POST /runs` 10/h/user · exports 5/h/user · imports 5/day/admin |
| SEC-WEB-006 | Spatial query caps | bbox ≤ 25 deg², time range ≤ 400 days, Postgres `statement_timeout = 15s` |
| SEC-WEB-007 | Output encoding | React default escaping; no `dangerouslySetInnerHTML`; Markdown in methodology rendered with a sanitizer |
| SEC-WEB-008 | CSV export | prefix cells starting with `= + - @ \t \r` with `'` (formula injection, §15.1) |
| SEC-WEB-009 | Error responses | no stack traces, SQL or file paths; `trace_id` only |

### D.7 Data store (`SEC-DB`)

| ID | Control |
|---|---|
| SEC-DB-001 | DB roles: `app_ro`, `ingest_writer` (REAL_OBSERVATION only), `sim_writer` (SIMULATED_* only), `inference_writer` (MODEL_INFERENCE only), `scorer` (only role with `sim_truth` SELECT), `migrator`. |
| SEC-DB-002 | DB-level `CHECK` constraints + triggers block cross-class `provenance_class` updates (defense in depth beyond app code). |
| SEC-DB-003 | Parameterized queries only; lint for f-string SQL. |
| SEC-DB-004 | Encryption at rest via host/volume; backups encrypted. |
| SEC-DB-005 | Backups daily, retain 7 daily + 4 weekly; **restore test** before the demo and monthly after. |

### D.8 Secrets (`SEC-SEC`)

| ID | Control |
|---|---|
| SEC-SEC-001 | Earthdata / Carbon Mapper / DB credentials from env or a secret manager; `.env` git-ignored; `.env.example` with placeholders only. |
| SEC-SEC-002 | `gitleaks` (or equivalent) as pre-commit hook **and** CI job; CI fails on findings. |
| SEC-SEC-003 | Rotate any credential used during the hackathon after the event. |
| SEC-SEC-004 | Log redaction filter for `Authorization`, cookies, `token`, `password`, `netrc` contents. |

### D.9 Supply chain and CI/CD (`SEC-SC`)

| ID | Control |
|---|---|
| SEC-SC-001 | Python lockfile with hashes (`uv lock` or `pip-tools --generate-hashes`); `npm ci` from lockfile. |
| SEC-SC-002 | Dependency scanning: `pip-audit` + `osv-scanner` (or `npm audit`) in CI; block on known critical vulnerabilities. |
| SEC-SC-003 | Renovate or Dependabot for updates, grouped weekly. |
| SEC-SC-004 | GitHub Actions pinned to full commit SHAs; workflow `permissions:` least privilege (default `contents: read`). |
| SEC-SC-005 | No `pull_request_target` with checkout of PR code. |
| SEC-SC-006 | SBOM (CycloneDX or SPDX) generated per release and included in bundle. |
| SEC-SC-007 | Release bundle signed (e.g., Sigstore `cosign` keyless) and accompanied by build provenance (SLSA-style; verify current level definitions). |
| SEC-SC-008 | Branch protection on `main`: PR required, 1 review, CI green, no force-push. |
| SEC-SC-009 | Static analysis: `ruff` + `bandit` (Python), `eslint` security rules (TS), `semgrep` baseline. |

### D.10 Runtime / containers (`SEC-RT`)

| ID | Control |
|---|---|
| SEC-RT-001 | Run as non-root; read-only root filesystem; writable `tmp` only. |
| SEC-RT-002 | Drop all Linux capabilities; default seccomp; no Docker socket mount. |
| SEC-RT-003 | Per-worker limits: CPU 2, memory 4 GB, solver process killed at 2 × deterministic-time budget. |
| SEC-RT-004 | Minimal base image (slim/distroless); image scanned in CI. |
| SEC-RT-005 | Only API and web exposed publicly; DB, Redis and scorer on a private network. |

### D.11 Audit and integrity (`SEC-AUD`)

| ID | Control |
|---|---|
| SEC-AUD-001 | `AuditEvent` gains `prev_hash` and `event_hash = SHA-256(canonical(event) ‖ prev_hash)`, forming a hash chain. Tampering breaks verification. |
| SEC-AUD-002 | `aether verify-audit --run-id` CLI command recomputes the chain; included in CI replay test. |
| SEC-AUD-003 | Run bundles include the head hash; signed manifest (SEC-SC-007). |
| SEC-AUD-004 | Audit retention: life of project; app logs 30 days. |

### D.12 Space-domain guardrails (`SEC-SPACE`)

| ID | Control |
|---|---|
| SEC-SPACE-001 | **No command path exists.** CI denylist check fails if code adds telecommand/ground-segment libraries or protocol encoders (e.g., CCSDS TC frame builders), or outbound connections to non-allowlisted hosts. |
| SEC-SPACE-002 | Every API object for a spacecraft carries `virtual: true` in P0/P1; schema rejects `virtual: false` outside archive-replay mode. |
| SEC-SPACE-003 | Any future real-mission integration (P2) requires a separate threat model against space-system guidance such as NIST IR 8270 / NIST IR 8401 and the Aerospace Corporation SPARTA framework (verify current versions), plus the operator's written authorization. |
| SEC-SPACE-004 | Archive replay of real instruments (EMIT/ISS) is read-only and can't enter the tasking queue (PRD §13.4), enforced in API and schema. |

### D.13 Abuse, ethics and disclosure (`SEC-ABUSE`, `SEC-GOV`)

| ID | Control |
|---|---|
| SEC-ABUSE-001 | No facility names displayed unless supplied by the upstream provider with attribution (PRD §4.4). |
| SEC-ABUSE-002 | Public view shows source *hypotheses* with uncertainty, never "violator/leaker" language (enforced via copy lint, see UX-COPY). |
| SEC-ABUSE-003 | Correction channel: published contact for operators/researchers to dispute an association; disputes logged and visible. |
| SEC-ABUSE-004 | Bulk export of source locations limited by rate limits and terms of use. |
| SEC-GOV-001 | `SECURITY.md` with a reporting address and 90-day coordinated disclosure. |
| SEC-GOV-002 | License manifest check in CI: export fails if any included record lacks a redistribution-permitted flag. |
| SEC-GOV-003 | If an LLM assistant is ever added: no tool execution, retrieved content never treated as instructions, output rendered as text, and labeled as such in UI. |
| SEC-GOV-004 | Security baseline target: OWASP ASVS Level 1 for the public demo, Level 2 for authenticated research deployment; OWASP API Security Top 10 (2023) reviewed per endpoint (verify current versions). |

---

## Part E — API parameters

### E.1 Conventions (`API-CONV`)

| ID | Parameter | Default |
|---|---|---|
| API-CONV-001 | Spec | OpenAPI 3.1, generated from Pydantic v2 models; spec committed and diffed in CI |
| API-CONV-002 | Versioning | URI major (`/api/v1`); additive changes only within v1 |
| API-CONV-003 | Deprecation | `Deprecation` and `Sunset` headers; ≥ 6 months notice after research v1 |
| API-CONV-004 | Errors | RFC 9457 `application/problem+json` with extensions `code` (the PRD's stable codes), `trace_id`, `details[]` |
| API-CONV-005 | Field naming | `snake_case`; units in name (`duration_s`) **or** `{value, unit}` objects, with one rule applied consistently (ADR) |
| API-CONV-006 | Nulls | nullable scientific fields always paired with `missing_reason` enum (`NOT_PROVIDED`, `NOT_APPLICABLE`, `CRITERIA_NOT_MET`, `INVALID_ACQUISITION`, `UNKNOWN`) |
| API-CONV-007 | Numbers | no NaN/Infinity; probabilities in `[0,1]`; IDs as strings |
| API-CONV-008 | Time | RFC 3339 UTC with `Z`; intervals as `start/end` (ISO 8601), open ends with `..` |
| API-CONV-009 | Geometry | GeoJSON (RFC 7946), `[lon, lat]`; bbox `minLon,minLat,maxLon,maxLat`; `minLon > maxLon` means antimeridian crossing |
| API-CONV-010 | Provenance | every resource carries `provenance_class`, `schema_version`, `source_refs[]` |
| API-CONV-011 | Interop | shape `/observations` to be compatible with STAC API / OGC API–Features query parameters (`bbox`, `datetime`, `limit`) so standard GIS tools work (P1) |

### E.2 Mechanics (`API-MECH`)

| ID | Parameter | Default |
|---|---|---|
| API-MECH-001 | Pagination | opaque cursor (`next`, `prev` links); `limit` default 50, max 500 |
| API-MECH-002 | Sorting | `sort=-acquisition_time_utc,id`; only indexed fields allowed |
| API-MECH-003 | Filtering | explicit query params only (no generic query language in P0) |
| API-MECH-004 | Idempotency | `Idempotency-Key` header on all POSTs; retained 24 h; same key + same body → same response; same key + different body → `409` |
| API-MECH-005 | Caching | `ETag` on all GETs; immutable run artifacts by hash → `Cache-Control: public, max-age=31536000, immutable` |
| API-MECH-006 | Rate-limit signaling | `429` + `Retry-After`; `RateLimit-Limit` / `RateLimit-Remaining` headers |
| API-MECH-007 | Tracing | accept/emit W3C `traceparent`; echo `X-Request-ID` |
| API-MECH-008 | Sync latency budget | p95 ≤ 300 ms for reads; anything that may exceed 2 s becomes an async job |
| API-MECH-009 | Request body limit | 1 MB (JSON); uploads via separate endpoint (SEC-IN-001) |
| API-MECH-010 | Event stream | SSE at `/runs/{id}/events/stream`; `id:` = `sequence_number`; resume with `Last-Event-ID`; heartbeat comment every 15 s |
| API-MECH-011 | Long exports | `POST /runs/{id}/exports` → job; `GET /exports/{id}` → signed short-lived download URL (15 min) |
| API-MECH-012 | Client generation | `openapi-typescript` types + runtime validation (e.g., `zod`) in the web app; responses that fail validation show an error, not partial data |

### E.3 Endpoints to add to PRD §12

| Method and path | Purpose | Role | Priority |
|---|---|---|---|
| `GET /runs` | list runs (filters: status, policy, scenario, owner) | researcher | P0 |
| `POST /runs/{id}/cancel` | cancel with partial audit kept | run_operator | P0 |
| `GET /runs/{id}/plans/{rev}/windows/{window_id}/explanation` | the §12.3 explanation object (fixes G-07) | researcher | P0 |
| `GET /sources/{id}` | single source hypothesis with associations | public | P0 |
| `GET /scenarios`, `GET /scenarios/{id}` | stored validated configs by hash | researcher | P0 |
| `GET /parameters` | resolved parameter registry for a scenario | public | P0 |
| `GET /citations`, `GET /methodology` | Screen G content, versioned | public | P0 |
| `GET /runs/{id}/audit` | hash-chained audit with verification status | researcher | P1 |
| `POST /evaluations` / `GET /evaluations/{id}` | scorer-only truth comparison (separate service) | evaluator | P1 |
| `GET /readyz` | readiness (DB, EOP file, fixtures present) separate from `/healthz` liveness | ops | P0 |

### E.4 Event schema additions

Add to §10.3: `NOT_OBSERVED`, `PLAN_REJECTED` (checker failure), `RUN_FAILED`, `RUN_CANCELLED`, `FORECAST_REVISED`, `PARAMETERS_RESOLVED`. Add fields: `schema_version`, `prev_hash`, `event_hash`, `cause_event_id` (for replan causality).

### E.5 API testing

- Contract tests: Schemathesis (or equivalent property-based OpenAPI fuzzing) against every endpoint in CI.
- Authorization matrix test: every endpoint × every role → expected allow/deny (generated from the SEC-RBAC table).
- Backward-compatibility check: OpenAPI diff fails CI on breaking changes within `v1`.

---

## Part F — UI/UX parameters: reliable and visibly human-made

The goal: a judge should read AETHER as a **tool built by people who use it**, not a generated dashboard. The most reliable way to get there is to design from the data outward, with constraints, rather than from a visual style inward.

### F.1 What makes a UI look AI-generated (avoid)

| Tell | Why it reads as generated | Do instead |
|---|---|---|
| Purple/indigo → cyan gradients, glowing neon on near-black "space" backgrounds | default output of most generators and templates | neutral gray UI; color reserved for data meaning |
| Glassmorphism, blurred translucent cards, heavy drop shadows | decorative, lowers legibility of numbers | flat surfaces, 1 px hairline dividers |
| Everything in identical rounded cards (`rounded-2xl`) in an even grid | no information hierarchy | panels sized by importance; tables and rules instead of cards |
| ✨ sparkle icons, "AI-powered", robot/brain icons, "Insights" panels | marketing signal, and PRD §0.9 forbids unvalidated "AI" labels | name the method: "Expected information gain (bits)" |
| Emoji as icons | inconsistent, unprofessional in an ops console | one line-icon set, used only where it aids recognition |
| Gradient text, animated counters, particle backgrounds, auto-rotating glowing globe | motion with no information | static by default; motion only to show state change |
| Vague copy: "Unlock insights", "seamlessly", "harness the power", "revolutionize", "cutting-edge", "next-generation", "game-changer" | generic filler | specific, testable statements (UX-COPY) |
| Placeholder-perfect data (round numbers, "Source A/B/C", lorem ipsum) | looks staged | real EMIT records and real computed outputs from day 1 |
| Everything centered, hero section on an internal tool | landing-page template applied to a console | left-aligned, dense, task-first |
| Inter + `slate-900` + `indigo-500` defaults untouched | the most common default stack | deliberate type and color choice (F.2) |
| Overprecise numbers (`0.8234`, `652.31 kg/h`) | implies certainty the model doesn't have | precision tied to uncertainty (UX-NUM) |

### F.2 Design tokens (`UX-TOK`)

| ID | Token | Default | Notes |
|---|---|---|---|
| UX-TOK-001 | UI typeface | IBM Plex Sans (alt: Source Sans 3) | Technical, open license, less overused than Inter. |
| UX-TOK-002 | Data/ID typeface | IBM Plex Mono (alt: JetBrains Mono) | IDs, UTC times, coordinates, hashes. |
| UX-TOK-003 | Long-form typeface | Source Serif 4 for methodology page | Makes Screen G read like a paper, a strong "human" signal. |
| UX-TOK-004 | Numerals | `font-variant-numeric: tabular-nums` everywhere numbers align | |
| UX-TOK-005 | Type scale (px) | 12 / 13 / 14 (base) / 16 / 20 / 24 | Dense console; no display sizes > 24 inside the app. |
| UX-TOK-006 | Spacing scale (px) | 4 / 8 / 12 / 16 / 24 / 32 | 4 px base grid. |
| UX-TOK-007 | Corner radius | 2 px (inputs), 4 px (popovers); 0 for panels | |
| UX-TOK-008 | Elevation | borders only; shadow only on popovers/menus | |
| UX-TOK-009 | Neutral palette | one gray ramp (10 steps), slightly warm | |
| UX-TOK-010 | Accent | one accent for interactive focus/selection only | Not used for data. |
| UX-TOK-011 | Categorical data colors | Okabe–Ito palette | Colorblind-safe. |
| UX-TOK-012 | Sequential raster colormap | `cividis` or `viridis` (never rainbow/`jet`) with labeled scale in ppm·m | |
| UX-TOK-013 | Contrast | text ≥ 4.5:1, large text and UI parts ≥ 3:1 | WCAG 2.2 AA. |
| UX-TOK-014 | Themes | light and dark, both designed; dark is a desaturated charcoal, not navy-with-glow | Test both in visual regression. |

### F.3 Provenance encoding (`UX-PROV`), the most important visual rule

Color is never the only signal (PRD §13.3). Each class gets **color + line style + text tag**:

| Class | Map stroke | Chart mark | Text tag | Where visible |
|---|---|---|---|---|
| `REAL_OBSERVATION` | solid 1.5 px | filled marker | `OBS` | everywhere |
| `MODEL_INFERENCE` | dashed | open marker + interval bar | `MODEL` | everywhere |
| `SIMULATED_OBSERVATION` | dotted + diagonal hatch fill | hatched marker | `SIM` | everywhere, plus persistent `SIMULATED MISSION` bar |
| `SIMULATED_GROUND_TRUTH` | double line | × marker | `TRUTH` | **evaluator view only**, full-width striped banner "EVALUATOR VIEW — HIDDEN TRUTH VISIBLE" |

Tags are real text (selectable, screen-reader readable), not icons. Exports and screenshots carry the same tags.

### F.4 Numbers, units and time (`UX-NUM`, `UX-TIME`)

| ID | Rule |
|---|---|
| UX-NUM-001 | Round a value to the same decimal place as its uncertainty's first significant digit: `650 ± 280 kg/h`, not `652.31 ± 281.7`. |
| UX-NUM-002 | Probabilities: 2 decimals; show `< 0.01` / `> 0.99` instead of `0.00` / `1.00`. Never show "certain". |
| UX-NUM-003 | Units always visible, separated by a thin space: `650 kg CH₄/h`. |
| UX-NUM-004 | Missing values show the reason: `— (rate not estimated: criteria not met)`, never `0` or blank. |
| UX-NUM-005 | Right-align numeric table columns; align on decimal point. |
| UX-TIME-001 | Primary time display: `2026-10-17 14:00:00Z` (UTC, 24 h, mono). Local time only in tooltip, labeled with zone. |
| UX-TIME-002 | Mission-relative time shown as `T+14h05m` alongside absolute time. |
| UX-TIME-003 | No relative "2 hours ago" for scientific records; allowed only for UI freshness ("data refreshed 40 s ago"). |

### F.5 Layout and components (`UX-LAY`)

| ID | Rule |
|---|---|
| UX-LAY-001 | Design target 1440 × 900; minimum supported 1280 × 720; tablet read-only; phone shows a methodology/summary view, not the console. |
| UX-LAY-002 | Persistent **status bar** (bottom): mode (`SIMULATED` / `REPLAY` / `ARCHIVE`), run ID (mono, copyable), scenario hash (short), UTC clock, data freshness, solver status. |
| UX-LAY-003 | Left nav with the 7 screens (A–G); keyboard shortcuts `1`–`7`. |
| UX-LAY-004 | Every map has a synchronized table (PRD §13.3); selecting in one selects in the other. |
| UX-LAY-005 | Table row height 28 px (compact) / 36 px (comfortable) toggle; virtualize above 500 rows. |
| UX-LAY-006 | Component inventory (build these, nothing else): data table, timeline/Gantt, map, interval chart, posterior plot, provenance tag, status pill, key–value inspector panel, diff view (old vs new plan), banner, toast, modal (rare), empty/error/loading states. |
| UX-LAY-007 | Asymmetric layouts chosen per screen by content priority, e.g., Screen E: 60 % candidate table / 40 % explanation inspector. |
| UX-LAY-008 | Charts: axis labels with units, direct labels over legends, credible-interval bands, no 3D, no pie/donut for comparisons, consistent y-axis across policy comparisons. |
| UX-LAY-009 | Map: muted basemap, scale bar, cursor coordinate readout (mono), attribution line, legend that matches UX-PROV. Globe (Cesium) is an optional toggle, never the default. |

### F.6 States and reliability (`UX-REL`)

| ID | Rule |
|---|---|
| UX-REL-001 | Every panel has explicit **loading, empty, error, stale, and replay** states, designed (not default spinners). Loading uses skeletons matching final layout. |
| UX-REL-002 | Empty states say why and what to do: "No feasible windows in this horizon. 41 candidates rejected: 28 `DARK`, 9 `POINTING`, 4 `STORAGE`. [View rejections]". |
| UX-REL-003 | Error boundary per panel; one failing panel never blanks the page. Error shows `trace_id` and a retry. |
| UX-REL-004 | Server is the source of truth: no client-side recomputation of metrics, posteriors or schedules (PRD §10.2). No optimistic updates for scientific state. |
| UX-REL-005 | GET requests retry 2× with backoff; POSTs never auto-retry without the same `Idempotency-Key`. |
| UX-REL-006 | Stale indicator if displayed data is older than the last known event (SSE gap or > 60 s without heartbeat). |
| UX-REL-007 | Runtime schema validation of every API response (API-MECH-012). |
| UX-REL-008 | Destructive/expensive actions (cancel run, new benchmark) need confirmation that states the cost ("~30 s deterministic solve, 15 sources × 2 spacecraft"). |
| UX-REL-009 | Weight changes on Screen E create a new versioned config; the UI shows the version diff, never edits in place. |
| UX-REL-010 | Replay mode is visually unmistakable: status-bar mode `REPLAY`, banner "Reproduced from run `abc123` recorded 2026-10-16 22:14Z", and disabled controls that would imply live computation. |

### F.7 Copy and microcopy (`UX-COPY`)

| ID | Rule |
|---|---|
| UX-COPY-001 | Write copy before visuals; every screen has a one-sentence purpose written at the top of its spec. |
| UX-COPY-002 | Use domain nouns: "acquisition", "pass", "off-nadir", "posterior", "valid non-detection". Define each once in a glossary tooltip. |
| UX-COPY-003 | Banned in UI and pitch (CI copy-lint over `frontend/src` and `docs/`): *AI-powered, seamless(ly), unlock, harness, revolutionize, cutting-edge, next-gen, game-changer, supercharge, effortless, magic, insights* (as a panel title), *leak fixed, violator, confirmed emitter*. |
| UX-COPY-004 | Buttons are verbs naming the result: "Re-solve plan", "Simulate next acquisition", "Export bundle"; never "Submit"/"Go". |
| UX-COPY-005 | Explanations are concrete: "Selected: highest expected gain (0.21 bits) among windows that fit remaining storage (18 GB left)". Never "AETHER thinks this is important". |
| UX-COPY-006 | Honest uncertainty language: "likely active (0.82)", "insufficient evidence", "not observed", following PRD §22.3. |

Before → after examples:

| Generic | AETHER |
|---|---|
| "AI-Powered Methane Insights ✨" | "Source beliefs — 15 hypotheses, updated T+14h" |
| "Our smart engine found the best targets!" | "Plan rev 3 · CP-SAT OPTIMAL · 7 of 212 windows selected" |
| "Leak detected!" | "Plume detected (EMIT V002, 2023-08-14 18:02Z) · rate not estimated" |
| "Something went wrong" | "Solver timed out before finding a feasible plan (UNKNOWN). Try fewer candidates or a longer limit. trace 7f3a…" |

### F.8 Motion and accessibility (`UX-A11Y`)

| ID | Rule |
|---|---|
| UX-A11Y-001 | Transitions ≤ 150 ms, used only for state change (selection, panel open, plan diff). No autoplay animation. |
| UX-A11Y-002 | Respect `prefers-reduced-motion`; orbit animation off by default. |
| UX-A11Y-003 | WCAG 2.2 AA: visible focus ring (2 px, accent), targets ≥ 24 × 24 px, full keyboard operation, skip link, landmarks. |
| UX-A11Y-004 | Map features reachable via synchronized table; charts have a "view as table" toggle. |
| UX-A11Y-005 | Screen-reader text for provenance tags includes the full class name ("simulated observation"). |
| UX-A11Y-006 | Automated: `axe` in Playwright with zero serious/critical violations; Lighthouse accessibility ≥ 95 on each screen. |

### F.9 Performance budgets (`UX-PERF`)

| ID | Budget |
|---|---|
| UX-PERF-001 | Initial JS ≤ 350 KB gzip excluding the map library; Cesium lazy-loaded only on globe toggle. |
| UX-PERF-002 | LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 on the demo laptop over local network. |
| UX-PERF-003 | > 10 000 map features → vector tiles or server-side clustering. |
| UX-PERF-004 | Plan diff and table filtering respond < 100 ms for 5 000 candidates. |

### F.10 Process that keeps it human (`UX-PROC`)

1. **Reference board first.** Collect 8–12 screenshots of real operations/science tools (e.g., NASA Worldview, flight-ops and air-traffic consoles, Bloomberg-style terminals, Observable notebooks, well-designed docs like Stripe's). Note *specific* traits to borrow (dense tables, mono timestamps, status bars). Don't copy any single product's branding.
2. **Paper or whiteboard wireframes** for screens A, E, F before any code. Photograph and keep them in `docs/design/`.
3. **Real data in every mock**: pinned EMIT fixtures and actual solver output.
4. **One domain-specific signature detail** instead of decoration, e.g., the timeline marks each orbital pass as a tick with its off-nadir angle, or the evidence panel reads like a lab notebook ledger.
5. **Your humanoid pass**: rewrite all copy in your team's own voice after F.7 is applied; read it aloud; cut anything you wouldn't say to a judge.
6. **Usability test**: 5 participants, think-aloud, tasks such as "Find why window w-104 was chosen" and "Is Source 7 inactive?" (correct answer: insufficient evidence). Target ≥ 80 % task success; fix the top 3 issues.
7. **Visual regression**: Playwright screenshots of each screen in light/dark, loading/empty/error/replay states, compared in CI.

---

## Part G — Reliability, operations and QA

### G.1 Operations (`OPS`)

| ID | Parameter | Default |
|---|---|---|
| OPS-001 | Environments | `local`, `demo` (frozen, offline-capable), `research` (authenticated) |
| OPS-002 | Demo availability target | 99 % during judging window; offline replay as fallback |
| OPS-003 | Health | `/healthz` liveness, `/readyz` readiness (DB, EOP file hash, fixtures, scorer reachable) |
| OPS-004 | Job retries | max 3, exponential backoff base 2 s, cap 60 s, full jitter; ingest only (never retry a solve silently) |
| OPS-005 | Upstream circuit breaker | open after 5 consecutive failures, half-open after 60 s |
| OPS-006 | Worker heartbeat / stale job reaper | 30 s / 10 min → `FAILED` with reason |
| OPS-007 | Checkpointing | after every event; restart resumes from last committed event (NFR-018) |
| OPS-008 | Logs | structured JSON with `run_id`, `trace_id`, `event_id`; no truth values (SEC-ISO-005) |
| OPS-009 | Telemetry | OpenTelemetry traces; metrics: solve time p50/p95, candidates, prune fraction, ingest rejects, 4xx/5xx, SSE clients |
| OPS-010 | Demo-day runbook | `docs/runbook.md`: start, offline switch, reset to known state, what to say if the solver is slow |

### G.2 Testing (`QA`)

| ID | Parameter | Default |
|---|---|---|
| QA-001 | Line coverage | ≥ 85 % for `orbit`, `belief`, `planning`, `simulation`, `provenance`; ≥ 70 % overall |
| QA-002 | Branch coverage | 100 % for the independent feasibility checker and provenance write guards |
| QA-003 | Mutation testing | `mutmut` (or equivalent) on the feasibility checker and Bayes update; ≥ 80 % mutants killed |
| QA-004 | Property tests | Hypothesis, ≥ 500 examples per invariant (probability conservation, storage never negative, no overlap) |
| QA-005 | Exhaustive cross-check | CP-SAT vs brute force on all instances with ≤ 12 candidates |
| QA-006 | CI duration | ≤ 10 min for PR checks; nightly full benchmark smoke |
| QA-007 | Required CI gates | lint, type-check (`mypy --strict` core, `tsc --strict`), unit, golden replay, import-linter, leakage canary, OpenAPI diff, Schemathesis, RBAC matrix, gitleaks, dependency audit, axe, visual regression |
| QA-008 | Fault injection | kill worker mid-solve, drop DB connection, corrupt fixture hash, network off |

---

## Part H — Governance and team

| ID | Item | Default |
|---|---|---|
| GOV-001 | Decision log | ADRs in `docs/adr/NNNN-title.md` for: units library, error format, field-unit convention, auth provider, deployment target, CP-SAT mode |
| GOV-002 | RACI | technical integrator owns provenance schema, units, events (PRD §18.2); named owner per parameter group in `parameters.yaml` |
| GOV-003 | Two-person review | required for `orbit/`, `planning/feasibility`, `belief/`, `provenance/`, auth code |
| GOV-004 | Claim review | every pitch slide and README claim checked against PRD §22.3 before presenting |
| GOV-005 | Repo hygiene | add `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CITATIONS.md`, `DATA_LICENSES.md`; fix README wording ("verify" → "corroborate") |
| GOV-006 | Hackathon time-box (48 h example) | 0–4 h fixtures + schemas + parameters registry · 4–14 h orbit + feasibility + checker · 14–24 h belief + EIG + CP-SAT · 24–32 h simulator loop + baseline · 32–40 h UI screens A, C, E, F · 40–44 h benchmark + export · 44–48 h offline rehearsal, claim review. Adjust to team size; the order matters more than the hours. |

---

## Part I — Where each new parameter group plugs into the PRD

| PRD section | Add / replace with |
|---|---|
| §5.2, §5.3, §6 | Part C.1–C.3 values into `configs/sensor_profiles/` and `spacecraft_profiles/` |
| §5.4–5.6 | C.4 |
| §7.3–7.4 | C.5, especially ENG-OPT-001…004 |
| §8.2, FR-SIM-002 | C.6 ENG-REP-* |
| §10.1 trust boundaries, §11.5 | D.4 SEC-ISO-*, D.7 SEC-DB-* |
| §10.3 events | E.4 |
| §12 API | E.1–E.5 |
| §13 UX | Part F |
| NFR-010, §15 | Part D |
| NFR-006/008/016/018 | G.1 |
| §17 | G.2 |
| §18, §20 | Part H, ADR list |
