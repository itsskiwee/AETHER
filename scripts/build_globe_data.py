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

from aether.config import load_scenario
from aether.orbit import _timescale, build_satellite
from skyfield.api import wgs84

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


def replay_runs() -> tuple[list[dict], list[dict]]:
    sources, runs = None, []
    for path in sorted(REPLAY.glob("*/run.json")):
        run = json.loads(path.read_bytes())
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--offline", action="store_true", help="do not refresh real elements"
    )
    args = ap.parse_args()
    previous = json.loads(OUT.read_bytes()) if OUT.exists() else {}
    cfg = load_scenario(ROOT / "configs/demo.yaml").model
    sources, runs = replay_runs()
    data = {
        "label": "REAL orbital context + SIMULATED MISSION replay; see layer labels",
        "real_satellites": real_elements(previous, args.offline),
        "plume_sources": sources,
        "simulation": {
            "scenario_id": cfg.scenario_id,
            "epoch_utc": cfg.simulation_epoch_utc.isoformat(),
            "horizon_hours": cfg.horizon_hours,
            "track_step_s": TRACK_STEP_S,
            "fleet": virtual_fleet(cfg),
            "runs": runs,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    for sat in data["real_satellites"]:
        print(sat["name"], sat["refresh_status"])
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
