"""Independent physical and resource feasibility checks for L8.

The checker owns its raw SGP4 initialization, TEME-to-ITRS transform, Sun geometry, and slew
calculation. It imports no code from ``aether.orbit``, the planner, or policy modules. Astropy
downloads are disabled; a pinned EOP data file and SHA-256 manifest are required.
"""

from __future__ import annotations

import hashlib
import json
import math
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.coordinates import ITRS, TEME, AltAz, CartesianRepresentation, EarthLocation, get_sun
from astropy.time import Time
from astropy.utils import iers
from sgp4.api import WGS72, Satrec, jday
from sgp4.earth_gravity import wgs72

from aether.config import ScenarioConfig, SensorProfile, SpacecraftProfile
from aether.contracts.models import (
    AcquisitionOption,
    ObservationWindow,
    Plan,
    ScheduleValidation,
    ScheduleViolation,
    Selection,
    Source,
)

CHECKER_VERSION = "0.2.0"
CheckReport = ScheduleValidation
EOP_DIRECTORY = Path(__file__).resolve().parents[3] / "data" / "eop"
EOP_FILENAME = "finals2000A.all"


def _stable_satellite_number(spacecraft_id: str) -> int:
    return zlib.crc32(spacecraft_id.encode("utf-8")) % 99999 + 1


def _build_satellite(profile: SpacecraftProfile) -> Satrec:
    """Initialize SGP4 from raw profile elements without using orbit-lane objects/helpers."""
    if not profile.virtual:
        raise ValueError("checker only propagates explicitly virtual spacecraft")
    orbit = profile.orbit
    if orbit.kind != "keplerian_sgp4init":
        raise NotImplementedError(f"unsupported orbit input: {orbit.kind}")
    epoch = orbit.epoch_utc
    jd, fraction = jday(
        epoch.year,
        epoch.month,
        epoch.day,
        epoch.hour,
        epoch.minute,
        epoch.second + epoch.microsecond / 1_000_000,
    )
    epoch_days = jd + fraction - 2433281.5
    semi_major_axis_km = wgs72.radiusearthkm + orbit.altitude_km
    mean_motion_rad_min = math.sqrt(wgs72.mu / semi_major_axis_km**3) * 60.0
    satellite = Satrec()
    satellite.sgp4init(
        WGS72,
        "i",
        _stable_satellite_number(profile.id),
        epoch_days,
        orbit.bstar,
        0.0,
        0.0,
        orbit.eccentricity,
        math.radians(orbit.arg_perigee_deg),
        math.radians(orbit.inclination_deg),
        math.radians(orbit.mean_anomaly_deg),
        mean_motion_rad_min,
        math.radians(orbit.raan_deg),
    )
    return satellite


@lru_cache(maxsize=1)
def _load_pinned_eop():
    """Load the pinned IERS table, verify its first-fetch hash, and disable network access."""
    table_path = EOP_DIRECTORY / EOP_FILENAME
    manifest_path = EOP_DIRECTORY / "manifest.json"
    if not table_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(
            f"Pinned EOP data is required at {table_path} with {manifest_path}; "
            "network downloads and unpinned fallbacks are disabled"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.get("sha256")
    if (
        manifest.get("filename") != EOP_FILENAME
        or manifest.get("byte_size") != table_path.stat().st_size
        or not isinstance(expected, str)
    ):
        raise ValueError(f"Invalid EOP manifest: {manifest_path}")
    actual = hashlib.sha256(table_path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"EOP SHA-256 mismatch: expected {expected}, got {actual}")
    iers.conf.auto_download = False
    iers.conf.auto_max_age = None
    return iers.IERS_A.open(str(table_path))


def _satellite_itrs_km(satellite: Satrec, when: Time) -> np.ndarray:
    # SGP4 epochs and elapsed time use UTC; UT1 belongs only in the Earth-frame
    # rotation performed by Astropy below. See Astropy's satellite coordinates example.
    utc = when.utc
    error, position_km, _ = satellite.sgp4(float(utc.jd1), float(utc.jd2))
    if error:
        raise RuntimeError(f"SGP4 propagation failed with error code {error}")
    teme = TEME(CartesianRepresentation(np.asarray(position_km) * u.km), obstime=when)
    return teme.transform_to(ITRS(obstime=when)).cartesian.xyz.to_value(u.km)


def _geometry(
    satellite: Satrec, source: Source, when: Time
) -> tuple[float, float, float, np.ndarray]:
    """Compute off-nadir, target elevation, solar elevation, and unit target LOS."""
    table = _load_pinned_eop()
    with iers.earth_orientation_table.set(table):
        location = EarthLocation.from_geodetic(source.lon * u.deg, source.lat * u.deg)
        target = location.get_itrs(obstime=when).cartesian.xyz.to_value(u.km)
        spacecraft = _satellite_itrs_km(satellite, when)
        los = target - spacecraft
        los_norm = np.linalg.norm(los)
        cosine = np.dot(los, -spacecraft) / (los_norm * np.linalg.norm(spacecraft))
        off_nadir_deg = math.degrees(math.acos(float(np.clip(cosine, -1.0, 1.0))))
        target_to_satellite = -los / los_norm
        lat = math.radians(source.lat)
        lon = math.radians(source.lon)
        up = np.array([math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)])
        elevation_deg = math.degrees(
            math.asin(float(np.clip(np.dot(target_to_satellite, up), -1.0, 1.0)))
        )
        sun_altaz = get_sun(when).transform_to(
            AltAz(obstime=when, location=location, pressure=0 * u.hPa)
        )
    return (
        off_nadir_deg,
        elevation_deg,
        float(sun_altaz.alt.to_value(u.deg)),
        los / los_norm,
    )


def _slew_seconds(
    first_los: np.ndarray, second_los: np.ndarray, profile: SpacecraftProfile
) -> float:
    angle_deg = math.degrees(math.acos(float(np.clip(np.dot(first_los, second_los), -1.0, 1.0))))
    return angle_deg / profile.attitude.slew_rate_deg_s + profile.attitude.settle_seconds


def check_schedule(
    plan: Plan,
    windows: Iterable[ObservationWindow] | Mapping[str, ObservationWindow],
    sources: Iterable[Source],
    spacecraft_profiles: Mapping[str, SpacecraftProfile],
    sensor_profile: SensorProfile,
    scenario: ScenarioConfig,
    *,
    committed: Iterable[ObservationWindow] = (),
    committed_selections: Iterable[Selection] = (),
) -> CheckReport:
    """Validate a Plan against exact option membership, independent geometry, and resources.

    Source hypotheses must be from the planner-visible model view. For every Selection, its
    ``option_id`` is looked up only inside the named window; a mismatch is UNKNOWN_OPTION.
    """
    window_items = tuple(windows.values()) if isinstance(windows, Mapping) else tuple(windows)
    committed_items = tuple(committed)
    committed_selection_items = tuple(committed_selections)
    window_items += committed_items
    window_map = {window.id: window for window in window_items}
    violations: list[ScheduleViolation] = []

    def add(rule: str, ids: Iterable[str], detail: str) -> None:
        violations.append(ScheduleViolation(option_ids=tuple(ids), rule=rule, detail=detail))

    if len(window_map) != len(window_items):
        add("DUPLICATE_WINDOW_ID", (), "supplied windows contain duplicate IDs")
    source_map = {source.id: source for source in sources}
    selected: list[tuple[ObservationWindow, AcquisitionOption, Source, SpacecraftProfile]] = []
    seen_window_ids: set[str] = set()

    selections = tuple(plan.selections) + committed_selection_items
    committed_by_window: dict[str, list] = defaultdict(list)
    for selection in committed_selection_items:
        committed_by_window[selection.window_id].append(selection)
    for committed_window in committed_items:
        fixed = committed_by_window.get(committed_window.id, [])
        if len(fixed) != 1:
            add(
                "COMMITTED_ACQUISITION",
                tuple(selection.option_id for selection in fixed),
                f"committed window {committed_window.id} requires exactly one explicit selection",
            )
    for selection in selections:
        window = window_map.get(selection.window_id)
        if window is None:
            add("UNKNOWN_WINDOW", (selection.option_id,), selection.window_id)
            add("UNKNOWN_OPTION", (selection.option_id,), "option has no supplied parent window")
            continue
        option = next(
            (item for item in window.options if item.option_id == selection.option_id), None
        )
        if option is None:
            add(
                "UNKNOWN_OPTION",
                (selection.option_id,),
                f"option does not belong to window {selection.window_id}",
            )
            continue
        if selection.window_id in seen_window_ids:
            add("WINDOW_LIMIT", (selection.option_id,), "multiple options selected for one window")
        seen_window_ids.add(selection.window_id)
        source = source_map.get(window.source_id)
        if source is None:
            add("UNKNOWN_SOURCE", (selection.option_id,), window.source_id)
            continue
        profile = spacecraft_profiles.get(window.spacecraft_id)
        if profile is None:
            add("UNKNOWN_SPACECRAFT", (selection.option_id,), window.spacecraft_id)
            continue
        if window.sensor_id != sensor_profile.id:
            add("UNKNOWN_SENSOR", (selection.option_id,), window.sensor_id)
            continue
        if not window.feasible:
            add("INFEASIBLE_WINDOW", (selection.option_id,), f"window {window.id} is infeasible")
        if option.start_utc < window.start_utc or option.end_utc > window.end_utc:
            add("OPTION_OUTSIDE_WINDOW", (selection.option_id,), f"option does not fit {window.id}")
        selected.append((window, option, source, profile))

    evaluated: list[tuple] = []
    satellites: dict[str, Satrec] = {}
    for window, option, source, profile in selected:
        if profile.id not in satellites:
            satellites[profile.id] = _build_satellite(profile)
        satellite = satellites[profile.id]
        start_time = Time(option.start_utc, scale="utc")
        end_time = Time(option.end_utc, scale="utc")
        start_geometry = _geometry(satellite, source, start_time)
        end_geometry = _geometry(satellite, source, end_time)
        for endpoint, geometry in (("start", start_geometry), ("end", end_geometry)):
            off_nadir, elevation, sun_elevation, _ = geometry
            if elevation <= 0:
                add("NOT_VISIBLE", (option.option_id,), f"target below horizon at {endpoint}")
            if off_nadir > profile.attitude.max_off_nadir_deg:
                add("POINTING", (option.option_id,), f"off-nadir limit exceeded at {endpoint}")
            if sun_elevation < sensor_profile.min_sun_elevation_deg:
                add("DARK", (option.option_id,), f"Sun elevation below limit at {endpoint}")
        evaluated.append((window, option, profile, start_geometry, end_geometry))

    by_spacecraft: dict[str, list[tuple]] = defaultdict(list)
    for item in evaluated:
        by_spacecraft[item[0].spacecraft_id].append(item)
    for spacecraft_id, tasks in by_spacecraft.items():
        profile = spacecraft_profiles[spacecraft_id]
        tasks.sort(key=lambda item: (item[1].start_utc, item[1].option_id))
        for previous, current in pairwise(tasks):
            _, first, _, _, first_end = previous
            _, second, _, second_start, _ = current
            if second.start_utc < first.end_utc:
                add("NO_OVERLAP", (first.option_id, second.option_id), "acquisitions overlap")
            else:
                available_s = (second.start_utc - first.end_utc).total_seconds()
                required_s = _slew_seconds(first_end[3], second_start[3], profile)
                if available_s + 1e-9 < required_s:
                    add(
                        "SLEW",
                        (first.option_id, second.option_id),
                        f"available {available_s:.6f}s; required {required_s:.6f}s",
                    )

    # PR-O03 limits visits in this solve, not over the mission lifetime. Completed
    # committed tasks still constrain resources and slew, but are outside this solve's
    # source count. Future frozen tasks remain in the count.
    committed_ids = {selection.option_id for selection in committed_selection_items}
    source_tasks = [
        item
        for item in evaluated
        if item[1].option_id not in committed_ids or item[1].end_utc > plan.created_at_sim_utc
    ]
    source_counts = Counter(window.source_id for window, *_ in source_tasks)
    for source_id, count in source_counts.items():
        if count > scenario.planner.max_visits_per_source_per_solve:
            ids = [
                option.option_id
                for window, option, *_ in source_tasks
                if window.source_id == source_id
            ]
            add("SOURCE_LIMIT", ids, f"source {source_id} has {count} visits")

    by_orbit: dict[tuple[str, int], list[tuple]] = defaultdict(list)
    for item in evaluated:
        window = item[0]
        by_orbit[(window.spacecraft_id, window.orbit_number)].append(item)
    by_satellite: dict[str, list[int]] = defaultdict(list)
    for sat_id, orbit_number in by_orbit:
        by_satellite[sat_id].append(orbit_number)
    for sat_id, orbit_numbers in by_satellite.items():
        profile = spacecraft_profiles[sat_id]
        max_usable_wh = profile.resources.battery_capacity_wh * (
            1.0 - profile.resources.min_state_of_charge
        )
        energy_available_wh = max(
            0.0,
            profile.resources.battery_capacity_wh
            * (profile.resources.initial_state_of_charge - profile.resources.min_state_of_charge),
        )
        previous_orbit: int | None = None
        for orbit_number in sorted(orbit_numbers):
            if previous_orbit is not None:
                energy_available_wh = min(
                    max_usable_wh,
                    energy_available_wh
                    + (orbit_number - previous_orbit) * profile.resources.orbit_average_recharge_wh,
                )
            tasks = by_orbit[(sat_id, orbit_number)]
            option_ids = tuple(item[1].option_id for item in tasks)
            if len(tasks) > profile.resources.max_acquisitions_per_orbit:
                add(
                    "PER_ORBIT_LIMIT",
                    option_ids,
                    f"orbit {orbit_number} exceeds acquisition limit",
                )
            data_used = sum(item[0].data_bytes for item in tasks)
            if data_used > profile.resources.storage_bytes:
                add("STORAGE", option_ids, f"orbit {orbit_number} uses {data_used} bytes")
            energy_used = sum(item[0].energy_wh for item in tasks)
            if energy_used > energy_available_wh + 1e-9:
                add("ENERGY", option_ids, f"orbit {orbit_number} uses {energy_used:.6f} Wh")
            energy_available_wh -= energy_used
            previous_orbit = orbit_number

    return CheckReport(
        plan_revision=plan.revision,
        ok=not violations,
        violations=tuple(violations),
        checker_version=CHECKER_VERSION,
    )
