"""Feasibility check (PR-F01): daylight access opportunities for candidate virtual constellations.

Independent of aether.orbit on purpose: lane L4 must reproduce these counts within +/-1 pass.
Run: python -I scripts/feasibility/pass_budget.py [horizon_hours]
Approximations: 10 s sampling, no refinement, 20 random Permian targets (seed 0).
"""

import math
import sys
from pathlib import Path

import numpy as np
from sgp4.api import WGS72, Satrec
from skyfield.api import EarthSatellite, load, load_file, wgs84

ts = load.timescale()
repo_root = Path(__file__).resolve().parents[2]
eph = load_file(str(repo_root / "data" / "ephemeris" / "de421.bsp"))
sun, earth = eph["sun"], eph["earth"]

EPOCH = ts.utc(2026, 10, 17)
ALT_KM = 500.0
RE = 6378.137
MU = 398600.4418
a = RE + ALT_KM
n_rad_s = math.sqrt(MU / a**3)
n_rad_min = n_rad_s * 60
INC = 97.40

# Sun right ascension at epoch -> RAAN for given LTDN
ra_sun = earth.at(EPOCH).observe(sun).apparent().radec()[0].hours * 15.0


def make_sat(name, ltdn_h, mean_anom_deg):
    ltan = (ltdn_h + 12) % 24
    raan = (ra_sun + (ltan - 12) * 15.0) % 360
    s = Satrec()
    s.sgp4init(
        WGS72,
        "i",
        99000 + len(name),
        EPOCH.ut1 - 2433281.5,
        0.0,
        0.0,
        0.0,
        0.0001,
        math.radians(0.0),
        math.radians(INC),
        math.radians(mean_anom_deg),
        n_rad_min,
        math.radians(raan),
    )
    return EarthSatellite.from_satrec(s, ts), raan


constellations = {
    "1 sat (10:30)": [("A", 10.5, 0)],
    "2 sats one plane": [("A", 10.5, 0), ("B", 10.5, 180)],
    "4 sats 2 planes": [
        ("A", 10.5, 0),
        ("B", 10.5, 180),
        ("C", 13.5, 90),
        ("D", 13.5, 270),
    ],
}
# Permian region grid of 20 pseudo-sources
rng = np.random.default_rng(0)
lons = rng.uniform(-104.3, -101.2, 20)
lats = rng.uniform(31.0, 33.2, 20)
targets = [wgs84.latlon(la, lo) for la, lo in zip(lats, lons, strict=True)]

H = int(sys.argv[1]) if len(sys.argv) > 1 else 72
t = ts.utc(2026, 10, 17, 0, 0, np.arange(0, H * 3600, 10))
sun_pos = {}
for max_off in (30, 40, 45):
    print(f"\n== horizon {H} h, max off-nadir {max_off} deg, min sun elev 20 deg ==")
    for cname, sats in constellations.items():
        pass_events = 0
        per_target_access = np.zeros(len(targets), int)
        for name, ltdn, M in sats:
            sat, raan = make_sat(name, ltdn, M)
            geo = sat.at(t)
            sp = geo.position.km
            in_pass_any = np.zeros(len(t), bool)
            for k, tg in enumerate(targets):
                tp = tg.at(t).position.km
                los = tp - sp
                off = np.degrees(
                    np.arccos(
                        np.clip(
                            np.sum(-sp * los, 0)
                            / (
                                np.linalg.norm(sp, axis=0) * np.linalg.norm(los, axis=0)
                            ),
                            -1,
                            1,
                        )
                    )
                )
                alt = (sat - tg).at(t).altaz()[0].degrees
                if k == 0 or k not in sun_pos:
                    sun_pos[k] = (
                        (earth + tg).at(t).observe(sun).apparent().altaz()[0].degrees
                    )
                ok = (off <= max_off) & (alt > 0) & (sun_pos[k] >= 20)
                # count access windows (rising edges)
                edges = np.sum(np.diff(ok.astype(int)) == 1) + int(ok[0])
                per_target_access[k] += edges
                in_pass_any |= ok
            pass_events += np.sum(np.diff(in_pass_any.astype(int)) == 1) + int(
                in_pass_any[0]
            )
        print(
            f"{cname:18s} regional passes={pass_events:3d}  "
            f"per-target windows: min={per_target_access.min()} "
            f"median={int(np.median(per_target_access))} max={per_target_access.max()} "
            f"total={per_target_access.sum()}"
        )
print(
    f"\nsun RA at epoch {ra_sun:.1f} deg; period {2 * math.pi / n_rad_s / 60:.2f} min"
)
