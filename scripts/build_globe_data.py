"""Build the static data behind the 3D globe view (``frontend/public/globe/globe-data.json``).

Run from the repository root:

    PYTHONPATH=backend python -m scripts.build_globe_data            # refresh real elements
    PYTHONPATH=backend python -m scripts.build_globe_data --offline  # keep cached elements

Three layers, kept apart and labelled:

* REAL: published CelesTrak GP orbital elements (OMM JSON) for the ISS, which carries NASA EMIT,
  Landsat 8, Landsat 9 and Sentinel-5P. The browser propagates them with SGP4 to the viewer's
  current time. These are modelled positions from public elements, not telemetry, and AETHER does
  not task or receive data from these spacecraft.
* REAL (historical): the 20 pinned EMIT V002 plume locations that place the simulated sources.
* SIMULATED: the virtual AETHER fleet's ground tracks over the demo horizon, computed with the
  project's Skyfield/SGP4 orbit model (``aether.orbit.build_satellite``), and the simulated
  acquisitions of the recorded demo runs.

Network goes only through ``scripts.live_context.fetch`` (netpolicy allowlist, timeouts, size
limit). A failed refresh keeps the previous elements and records the failure; it never invents
positions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
from aether.config import load_scenario
from aether.orbit import _timescale, build_satellite, load_ephemeris
from skyfield.api import EarthSatellite, wgs84

from scripts.live_context import fetch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend/public/globe/globe-data.json"
REPLAY = ROOT / "data/fixtures/hosted_replay"
# NORAD catalogue numbers of the real spacecraft shown for context.
REAL = {
    25544: ("ISS (ZARYA)", "Carries NASA EMIT, the source of the pinned plume records"),
    39084: ("LANDSAT 8", "NASA/USGS land imaging"),
    49260: ("LANDSAT 9", "NASA/USGS land imaging"),
    42969: ("SENTINEL-5P", "ESA/Copernicus TROPOMI: daily global methane columns"),
}
GP_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR={}&FORMAT=JSON"
TRACK_STEP_S = 60
PLUMES = ROOT / "data/normalized/emit_permian_plumes.json"
# PR-LIVE02: swath widths (km) for geometric pass opportunities, look-ahead and sampling.
SWATH_KM = {25544: 75.0, 39084: 185.0, 49260: 185.0, 42969: 2600.0}
PASS_LOOKAHEAD_H = 72
PASS_STEP_S = 10
EARTH_RADIUS_KM = 6371.0088
# The configured Permian region (configs/regions/permian.yaml), queried in NASA CMR.
CMR_URL = (
    "https://cmr.earthdata.nasa.gov/search/granules.json?short_name=EMITL2BCH4PLM&version=002"
    "&bounding_box=-104.5,30.8,-101.0,33.5&page_size=20&sort_key=-start_date"
)


def real_elements(previous: dict, offline: bool) -> list[dict]:
    cached = {item["norad_id"]: item for item in previous.get("real_satellites", [])}
    out = []
    for norad, (name, role) in REAL.items():
        url = GP_URL.format(norad)
        entry = {"norad_id": norad, "name": name, "role": role, "url": url}
        try:
            if offline:
                raise RuntimeError("offline: refresh not attempted")
            data = fetch(url)
            omm = json.loads(data)[0]
            entry |= {
                "omm": omm,
                "retrieved_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                "sha256": hashlib.sha256(data).hexdigest(),
                "refresh_status": "OK",
            }
        except (OSError, RuntimeError, ValueError, KeyError, IndexError) as exc:
            # Keep the last good elements; never fabricate positions.
            old = cached.get(norad)
            if old is None or "omm" not in old:
                entry |= {"refresh_status": f"UNAVAILABLE: {exc}"}
            else:
                entry = old | {"refresh_status": f"CACHED: {exc}"}
        out.append(entry)
    return out


def emit_records() -> list[dict]:
    """The 20 pinned EMIT V002 records exactly as normalized (REAL_OBSERVATION)."""
    keep = ("id", "native_id", "acquisition_time_utc", "lat", "lon", "emission_rate_kg_h",
            "emission_rate_uncertainty_kg_h", "missing_rate_reason", "provider",
            "dataset_version", "provenance_class")  # fmt: skip
    return [{k: r.get(k) for k in keep} for r in json.loads(PLUMES.read_bytes())]


def emit_recent(previous: dict, offline: bool) -> dict:
    """Newest EMIT CH4 plume granules over the Permian box from NASA CMR (catalogue metadata)."""
    try:
        if offline:
            raise RuntimeError("offline: refresh not attempted")
        data = fetch(CMR_URL)
        entries = json.loads(data)["feed"]["entry"]
        return {
            "url": CMR_URL,
            "retrieved_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "sha256": hashlib.sha256(data).hexdigest(),
            "refresh_status": "OK",
            "granules": [
                {
                    "title": e.get("title"),
                    "time_start": e.get("time_start"),
                    "updated": e.get("updated"),
                    "data_url": next(
                        (
                            link["href"]
                            for link in e.get("links", [])
                            if link.get("href", "").startswith("https://")
                            and link.get("rel", "").endswith("/data#")
                        ),
                        None,
                    ),
                }
                for e in entries
            ],
        }
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        old = previous.get("emit_recent")
        if old and old.get("granules") is not None:
            return old | {"refresh_status": f"CACHED: {exc}"}
        return {"url": CMR_URL, "refresh_status": f"UNAVAILABLE: {exc}", "granules": []}


def real_passes(sats: list[dict], sites: list[dict], start: datetime) -> list[dict]:
    """Geometric opportunities: sub-satellite point within half the swath of a plume site."""
    ts = _timescale()
    eph = load_ephemeris()
    n = int(PASS_LOOKAHEAD_H * 3600 // PASS_STEP_S) + 1
    t = ts.from_datetimes(
        [start + timedelta(seconds=i * PASS_STEP_S) for i in range(n)]
    )
    site_lat = np.radians([s["lat"] for s in sites])[None, :]
    site_lon = np.radians([s["lon"] for s in sites])[None, :]
    centre = wgs84.latlon(float(np.mean([s["lat"] for s in sites])),
                          float(np.mean([s["lon"] for s in sites])))  # fmt: skip
    out = []
    for sat in sats:
        if "omm" not in sat:
            continue
        es = EarthSatellite.from_omm(ts, sat["omm"])
        sub = wgs84.subpoint_of(es.at(t))
        lat = sub.latitude.radians[:, None]
        lon = sub.longitude.radians[:, None]
        hav = (np.sin((site_lat - lat) / 2) ** 2
               + np.cos(lat) * np.cos(site_lat) * np.sin((site_lon - lon) / 2) ** 2)  # fmt: skip
        dist = 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(hav))
        inside = dist <= SWATH_KM[sat["norad_id"]] / 2
        rows = np.flatnonzero(inside.any(axis=1))
        if rows.size == 0:
            continue
        groups = np.split(rows, np.flatnonzero(np.diff(rows) > 1) + 1)
        for g in groups:
            best = g[np.argmin(dist[g].min(axis=1))]
            when = t[int(best)]
            sun_alt = (
                (eph["earth"] + centre)
                .at(when)
                .observe(eph["sun"])
                .apparent()
                .altaz()[0]
            )
            covered = sorted(
                {sites[j]["id"] for j in np.flatnonzero(inside[g].any(axis=0))}
            )
            out.append(
                {
                    "norad_id": sat["norad_id"],
                    "satellite": sat["name"],
                    "start_utc": t[int(g[0])]
                    .utc_datetime()
                    .isoformat(timespec="seconds"),
                    "end_utc": t[int(g[-1])]
                    .utc_datetime()
                    .isoformat(timespec="seconds"),
                    "closest_utc": when.utc_datetime().isoformat(timespec="seconds"),
                    "sites_in_swath": covered,
                    "min_ground_distance_km": round(float(dist[g].min()), 1),
                    "sun_elevation_deg": round(float(sun_alt.degrees), 1),
                    "daylit": bool(sun_alt.degrees > 0),
                }
            )
    return sorted(out, key=lambda p: p["closest_utc"])


def virtual_fleet(cfg) -> list[dict]:
    ts = _timescale()
    start = cfg.simulation_epoch_utc
    steps = int(cfg.horizon_hours * 3600 // TRACK_STEP_S) + 1
    times = [start + timedelta(seconds=i * TRACK_STEP_S) for i in range(steps)]
    t = ts.from_datetimes(times)
    fleet = []
    for sc_id, profile in sorted(cfg.spacecraft.items()):
        position = build_satellite(profile).at(t)
        sub = wgs84.subpoint_of(position)
        alt = wgs84.height_of(position).km
        fleet.append(
            {
                "id": sc_id,
                "altitude_km": float(profile.orbit.altitude_km),
                "inclination_deg": float(profile.orbit.inclination_deg),
                "track": [
                    [round(float(la), 4), round(float(lo), 4), round(float(h), 1)]
                    for la, lo, h in zip(
                        sub.latitude.degrees, sub.longitude.degrees, alt
                    )
                ],
            }
        )
    return fleet


def replay_runs(directory: Path = REPLAY) -> tuple[list[dict], list[dict]]:
    sources, runs = None, []
    for path in sorted(directory.glob("*/run.json")):
        data = path.read_bytes()
        run = json.loads(data)
        if sources is None:
            sources = [
                {
                    "id": s["id"],
                    "lat": s["lat"],
                    "lon": s["lon"],
                    "plume_id": s.get("seeded_from_plume_id"),
                }
                for s in run["sources"]
            ]
        runs.append(
            {
                "run_id": run["run_id"],
                "policy_id": run["policy_id"],
                "run_sha256": hashlib.sha256(data).hexdigest(),
                "acquisitions": [
                    {
                        "time_utc": a["time_utc"],
                        "spacecraft_id": a["spacecraft_id"],
                        "source_id": a["source_id"],
                        "outcome": a["outcome"],
                    }
                    for a in run["acquisitions"]
                ],
            }
        )
    return sources or [], runs


def mission(label: str, run_dir: Path, family: Path | None = None) -> dict | None:
    """One recorded simulated mission: its fleet tracks, every source and each policy's looks."""
    sources, runs = replay_runs(run_dir)
    if not runs:
        print(f"mission skipped (no runs in {run_dir.relative_to(ROOT)}): {label}")
        return None
    cfg = load_scenario(ROOT / "configs/demo.yaml", family).model
    return {
        "label": label,
        "scenario_id": cfg.scenario_id,
        "family": cfg.family,
        "epoch_utc": cfg.simulation_epoch_utc.isoformat(),
        "horizon_hours": cfg.horizon_hours,
        "track_step_s": TRACK_STEP_S,
        "run_dir": run_dir.relative_to(ROOT).as_posix(),
        "sources": sources,
        "fleet": virtual_fleet(cfg),
        "runs": runs,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--offline", action="store_true", help="do not refresh real elements"
    )
    args = ap.parse_args()
    previous = json.loads(OUT.read_bytes()) if OUT.exists() else {}
    cfg = load_scenario(ROOT / "configs/demo.yaml").model
    sources, runs = replay_runs()
    sats = real_elements(previous, args.offline)
    built = datetime.now(UTC).replace(microsecond=0)
    records = emit_records()
    data = {
        "label": "REAL orbital context + SIMULATED MISSION replay; see layer labels",
        "built_at_utc": built.isoformat(),
        "real_satellites": sats,
        "emit_records": records,
        "emit_recent": emit_recent(previous, args.offline),
        "real_passes": {
            "from_utc": built.isoformat(),
            "lookahead_hours": PASS_LOOKAHEAD_H,
            "swath_km": {str(k): v for k, v in SWATH_KM.items()},
            "note": "Geometric opportunity only (PR-LIVE02); not an acquisition forecast or tasking",
            "passes": real_passes(sats, records, built),
        },
        "plume_sources": sources,
        "simulation": {
            "scenario_id": cfg.scenario_id,
            "epoch_utc": cfg.simulation_epoch_utc.isoformat(),
            "horizon_hours": cfg.horizon_hours,
            "track_step_s": TRACK_STEP_S,
            "fleet": virtual_fleet(cfg),
            "runs": runs,
        },
        # Selectable missions on the globe. The 168 h demo is regenerated locally (runs/ is not
        # tracked); each run is identified by its run_id and the SHA-256 of its run.json.
        "missions": [
            m
            for m in (
                mission("72-hour demo · 20 sites", REPLAY),
                mission(
                    "168-hour demo · 60 sites",
                    ROOT / "runs/demo-h168",
                    ROOT / "configs/scenarios/h168_long_horizon.yaml",
                ),
            )
            if m is not None
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    for sat in data["real_satellites"]:
        print(sat["name"], sat["refresh_status"])
    print(
        "EMIT recent:",
        data["emit_recent"]["refresh_status"],
        len(data["emit_recent"]["granules"]),
    )
    print("real passes:", len(data["real_passes"]["passes"]))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
