"""SGP4 propagation and visibility windows for explicitly virtual spacecraft.

The orbit lane owns the geometric portion of candidate generation. It uses SGP4 for satellite
motion and Skyfield for topocentric geometry, the Sun position, and frame transformations. It does
not infer that a real spacecraft is taskable and does not make weather or resource decisions.

Public functions:

* ``build_satellite(profile)`` builds a deterministic SGP4/Skyfield ``EarthSatellite``.
* ``load_ephemeris()`` opens only a local DE421 file whose SHA-256 is recorded in a sidecar.
* ``generate_windows(cfg, sources, start_utc, end_utc)`` returns usable and rejected access
  windows, with discrete acquisition options whose LOS is evaluated at each option start.
* ``slew_time_s(prev, nxt, attitude)`` estimates the slew between option LOS vectors. The
  independent schedule checker must implement its own calculation.

Window discovery uses the configured coarse step (2 s in the current registered scenario), then
bisects each detected boundary to the configured tolerance. Skyfield's built-in timescale tables
are used so a satellite propagation or offline geometry call never downloads Earth-orientation
data. Solar illumination additionally requires the pinned local DE421 ephemeris.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import zlib
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from sgp4.api import Satrec, WGS72
from sgp4.earth_gravity import wgs72
from sgp4.ext import jday
from skyfield.api import EarthSatellite, load, load_file, wgs84
from skyfield.framelib import itrs

from aether.config import ScenarioConfig
from aether.contracts.enums import RejectionReason
from aether.contracts.models import (
    AcquisitionOption,
    AttitudeConfig,
    ObservationWindow,
    Source,
    SpacecraftProfile,
)

_JULIAN_DATE_1949_EPOCH = 2433281.5
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_LTDN_TOLERANCE_S = 120.0  # ORB-02: registered ±2 min


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def _timescale() -> Any:
    """Use Skyfield's packaged time data; do not fetch IERS data at runtime."""
    return load.timescale(builtin=True)


@lru_cache(maxsize=1)
def load_ephemeris() -> Any:
    """Load local DE421 after verifying its SHA-256 sidecar.

    Accepted sidecars are ``de421.bsp.sha256`` in standard ``sha256sum`` format, or
    ``manifest.json`` containing either ``{"sha256": "…"}`` or
    ``{"de421.bsp": {"sha256": "…"}}``. No network fallback is permitted.
    """
    directory = _repo_root() / "data" / "ephemeris"
    ephemeris_path = directory / "de421.bsp"
    if not ephemeris_path.is_file():
        raise FileNotFoundError(
            f"Pinned ephemeris is missing: {ephemeris_path}; install the registered local DE421 "
            "artifact before generating solar-illumination windows"
        )

    expected: str | None = None
    checksum_path = directory / "de421.bsp.sha256"
    manifest_path = directory / "manifest.json"
    if checksum_path.is_file():
        parts = checksum_path.read_text(encoding="ascii").strip().split()
        expected = parts[0] if parts else None
    elif manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = manifest.get("de421.bsp", manifest)
        expected = entry.get("sha256") if isinstance(entry, dict) else None
    if not expected or not _SHA256_RE.fullmatch(expected):
        raise ValueError(f"Missing or invalid DE421 SHA-256 manifest in {directory}")

    digest = hashlib.sha256()
    with ephemeris_path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual.lower() != expected.lower():
        raise ValueError(
            f"DE421 SHA-256 mismatch: expected {expected.lower()}, got {actual}"
        )
    return load_file(str(ephemeris_path))


def _ensure_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(UTC)


def _stable_satellite_number(spacecraft_id: str) -> int:
    """Map an ID to a repeatable positive NORAD-like number without Python hash randomization."""
    return zlib.crc32(spacecraft_id.encode("utf-8")) % 99999 + 1


def build_satellite(profile: SpacecraftProfile) -> EarthSatellite:
    """Create a Skyfield satellite from the scenario's virtual Keplerian elements.

    ``altitude_km`` is measured above the WGS-72 equatorial radius, matching the gravity model
    used by SGP4. The configured epoch and angular elements are passed directly to SGP4.
    """
    if not profile.virtual:
        raise ValueError("only explicitly virtual spacecraft may be propagated for task planning")
    orbit = profile.orbit
    if orbit.kind != "keplerian_sgp4init":
        raise NotImplementedError(f"unsupported orbit input kind: {orbit.kind}")

    epoch = _ensure_utc(orbit.epoch_utc, "orbit.epoch_utc")
    seconds = epoch.second + epoch.microsecond / 1_000_000
    jd, fraction = jday(
        epoch.year, epoch.month, epoch.day, epoch.hour, epoch.minute, seconds
    )
    epoch_days = jd + fraction - _JULIAN_DATE_1949_EPOCH
    semi_major_axis_km = wgs72.radiusearthkm + orbit.altitude_km
    mean_motion_rad_min = math.sqrt(wgs72.mu / semi_major_axis_km**3) * 60.0

    record = Satrec()
    record.sgp4init(
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
    return EarthSatellite.from_satrec(record, _timescale())


def _check_sgp4(satellite: EarthSatellite, times: Any) -> None:
    """Raise with the SGP4 error code rather than accepting an invalid propagated state."""
    if np.ndim(times.whole) == 0:
        error_code, _, _ = satellite.model.sgp4(
            float(times.whole), float(times.ut1_fraction)
        )
        if error_code:
            raise RuntimeError(f"SGP4 propagation failed with error code {error_code}")
        return
    _, _, errors = satellite.model.sgp4_array(times.whole, times.ut1_fraction)
    error_codes = np.asarray(errors)
    if np.any(error_codes != 0):
        first = int(error_codes.flat[np.flatnonzero(error_codes)[0]])
        raise RuntimeError(f"SGP4 propagation failed with error code {first}")


def _geometry_series(
    satellite: EarthSatellite,
    source: Source,
    times: Any,
    earth: Any,
    sun: Any,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return off-nadir, target elevation, solar elevation and unit LOS arrays."""
    _check_sgp4(satellite, times)
    site = wgs84.latlon(latitude_degrees=source.lat, longitude_degrees=source.lon)
    sat_position = np.asarray(satellite.at(times).frame_xyz(itrs).km)
    ground_position = np.asarray((earth + site).at(times).frame_xyz(itrs).km)
    los = ground_position - sat_position
    nadir = -sat_position
    cosine = np.sum(los * nadir, axis=0) / (
        np.linalg.norm(los, axis=0) * np.linalg.norm(nadir, axis=0)
    )
    off_nadir_deg = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))

    target_elevation_deg = (satellite - site).at(times).altaz()[0].degrees
    observer = earth + site
    sun_elevation_deg = observer.at(times).observe(sun).apparent().altaz()[0].degrees
    los_unit = los / np.linalg.norm(los, axis=0)
    return (
        np.asarray(off_nadir_deg),
        np.asarray(target_elevation_deg),
        np.asarray(sun_elevation_deg),
        np.asarray(los_unit),
    )


def _scalar_geometry(
    satellite: EarthSatellite,
    source: Source,
    when_utc: datetime,
    earth: Any,
    sun: Any,
) -> tuple[float, float, float, tuple[float, float, float]]:
    ts = _timescale().from_datetime(when_utc)
    off, elevation, sun_elevation, los_unit = _geometry_series(
        satellite, source, ts, earth, sun
    )
    return (
        float(off),
        float(elevation),
        float(sun_elevation),
        tuple(float(x) for x in los_unit),
    )


def _reason_for_state(
    off_nadir_deg: float,
    elevation_deg: float,
    sun_elevation_deg: float,
    max_off_nadir_deg: float,
    min_sun_elevation_deg: float,
    is_blackout: bool,
) -> tuple[RejectionReason, ...] | None:
    """Classify one instant; None means the target is below the geometric horizon."""
    if elevation_deg <= 0.0:
        return None
    reasons: list[RejectionReason] = []
    if off_nadir_deg > max_off_nadir_deg:
        reasons.append(RejectionReason.POINTING)
    if sun_elevation_deg < min_sun_elevation_deg:
        reasons.append(RejectionReason.DARK)
    if is_blackout:
        reasons.append(RejectionReason.BLACKOUT)
    return tuple(reasons)


def _sample_datetimes(
    start_utc: datetime, end_utc: datetime, step_s: float
) -> list[datetime]:
    span_s = (end_utc - start_utc).total_seconds()
    count = int(math.floor(span_s / step_s))
    samples = [start_utc + timedelta(seconds=i * step_s) for i in range(count + 1)]
    if samples[-1] != end_utc:
        samples.append(end_utc)
    return samples


def _in_blackout(profile: SpacecraftProfile, when_utc: datetime) -> bool:
    return any(
        blackout.start_utc <= when_utc < blackout.end_utc for blackout in profile.blackouts
    )


def _refine_transition(
    satellite: EarthSatellite,
    source: Source,
    left_utc: datetime,
    right_utc: datetime,
    right_state: tuple[RejectionReason, ...] | None,
    profile: SpacecraftProfile,
    sensor: Any,
    earth: Any,
    sun: Any,
    tolerance_s: float,
) -> datetime:
    """Bisect a detected state transition until its time bracket meets the configured tolerance."""
    left = left_utc
    right = right_utc
    while (right - left).total_seconds() > tolerance_s:
        mid = left + (right - left) / 2
        off, elevation, sun_elevation, _ = _scalar_geometry(
            satellite, source, mid, earth, sun
        )
        state = _reason_for_state(
            off,
            elevation,
            sun_elevation,
            profile.attitude.max_off_nadir_deg,
            sensor.min_sun_elevation_deg,
            _in_blackout(profile, mid),
        )
        if state == right_state:
            right = mid
        else:
            left = mid
    return right


def _minimum_off_nadir_time(
    satellite: EarthSatellite,
    source: Source,
    sample_times: list[datetime],
    sampled_off_nadir_deg: np.ndarray,
    first_index: int,
    last_index: int,
    earth: Any,
    sun: Any,
    tolerance_s: float,
) -> tuple[datetime, float]:
    """Refine the lowest sampled off-nadir point with a bounded golden-section search."""
    # The minimum is normally near closest approach. Bracket it by adjacent samples so the search
    # cannot jump to a different pass or across a daylight/blackout boundary.
    local_index = int(np.argmin(sampled_off_nadir_deg[first_index : last_index + 1]))
    center_index = first_index + local_index
    lo = sample_times[max(first_index, center_index - 1)]
    hi = sample_times[min(last_index, center_index + 1)]
    if hi <= lo:
        return sample_times[center_index], float(sampled_off_nadir_deg[center_index])

    ratio = (math.sqrt(5.0) - 1.0) / 2.0

    def objective(when: datetime) -> float:
        return _scalar_geometry(satellite, source, when, earth, sun)[0]

    x1 = hi - (hi - lo) * ratio
    x2 = lo + (hi - lo) * ratio
    f1, f2 = objective(x1), objective(x2)
    while (hi - lo).total_seconds() > tolerance_s:
        if f1 <= f2:
            hi, x2, f2 = x2, x1, f1
            x1 = hi - (hi - lo) * ratio
            f1 = objective(x1)
        else:
            lo, x1, f1 = x1, x2, f2
            x2 = lo + (hi - lo) * ratio
            f2 = objective(x2)
    best_time = x1 if f1 <= f2 else x2
    return best_time, min(f1, f2)


def _option_times(
    start_utc: datetime,
    end_utc: datetime,
    exposure_s: float,
    option_step_s: float,
    max_options: int,
    preferred_utc: datetime,
) -> list[datetime]:
    last_start = end_utc - timedelta(seconds=exposure_s)
    if last_start < start_utc:
        return []
    span_s = (last_start - start_utc).total_seconds()
    count = int(math.floor(span_s / option_step_s))
    candidates = [start_utc + timedelta(seconds=i * option_step_s) for i in range(count + 1)]
    if not candidates or candidates[-1] != last_start:
        candidates.append(last_start)
    candidates.append(min(max(preferred_utc, start_utc), last_start))
    candidates = sorted(set(candidates))
    if len(candidates) > max_options:
        selected_indices = np.linspace(0, len(candidates) - 1, max_options, dtype=int)
        selected = {candidates[int(i)] for i in selected_indices}
        preferred = min(candidates, key=lambda t: abs((t - preferred_utc).total_seconds()))
        selected.add(preferred)
        while len(selected) > max_options:
            removable = [t for t in selected if t != preferred]
            # Keep endpoints whenever possible; remove the selected interior time closest to a
            # neighbor, which avoids clustering the retained option grid.
            removable.sort(
                key=lambda t: min(
                    abs((t - other).total_seconds()) for other in selected if other != t
                )
            )
            selected.remove(removable[0])
        candidates = sorted(selected)
    return candidates


def _window_id(
    spacecraft_id: str, sensor_id: str, source_id: str, start_utc: datetime, index: int
) -> str:
    stamp = start_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return f"{spacecraft_id}:{sensor_id}:{source_id}:{stamp}:{index}"


def _make_window(
    cfg: ScenarioConfig,
    profile: SpacecraftProfile,
    sensor: Any,
    source: Source,
    satellite: EarthSatellite,
    pass_id: str,
    orbit_number: int,
    start_utc: datetime,
    end_utc: datetime,
    reasons: tuple[RejectionReason, ...],
    sample_times: list[datetime],
    sampled_off_nadir_deg: np.ndarray,
    first_index: int,
    last_index: int,
    earth: Any,
    sun: Any,
    tolerance_s: float,
    index: int,
) -> ObservationWindow:
    min_time, min_off = _minimum_off_nadir_time(
        satellite,
        source,
        sample_times,
        sampled_off_nadir_deg,
        first_index,
        last_index,
        earth,
        sun,
        tolerance_s,
    )
    duration_s = sensor.exposure_seconds
    energy_wh = sensor.costs.energy_wh_per_scene
    data_bytes = sensor.costs.data_bytes_per_scene

    if not reasons:
        min_length_s = duration_s + profile.attitude.settle_seconds
        if (end_utc - start_utc).total_seconds() + 1e-9 < min_length_s:
            reasons = (RejectionReason.SHORT_WINDOW,)

    window_id = _window_id(profile.id, sensor.id, source.id, start_utc, index)
    options: list[AcquisitionOption] = []
    if not reasons:
        option_starts = _option_times(
            start_utc,
            end_utc,
            duration_s,
            cfg.window_search.option_step_s,
            cfg.window_search.max_options_per_window,
            min_time,
        )
        for option_index, option_start in enumerate(option_starts):
            off, _, sun_elevation, los_unit = _scalar_geometry(
                satellite, source, option_start, earth, sun
            )
            option_end = option_start + timedelta(seconds=duration_s)
            options.append(
                AcquisitionOption(
                    id=f"{window_id}#{option_index}",
                    window_id=window_id,
                    index=option_index,
                    start_utc=option_start,
                    end_utc=option_end,
                    off_nadir_deg=off,
                    sun_elevation_deg=sun_elevation,
                    los_unit_ecef=los_unit,
                )
            )
    if not reasons and not options:
        reasons = (RejectionReason.SHORT_WINDOW,)

    return ObservationWindow(
        id=window_id,
        spacecraft_id=profile.id,
        sensor_id=sensor.id,
        source_id=source.id,
        start_utc=start_utc,
        end_utc=end_utc,
        pass_id=pass_id,
        orbit_number=orbit_number,
        feasible=not reasons,
        rejection_reasons=reasons,
        min_off_nadir_deg=min_off,
        options=tuple(options),
        duration_s=duration_s,
        energy_wh=energy_wh,
        data_bytes=data_bytes,
    )


def _orbit_number(satellite: EarthSatellite, when_utc: datetime) -> int:
    epoch_utc = satellite.epoch.utc_datetime().astimezone(UTC)
    elapsed_minutes = (when_utc - epoch_utc).total_seconds() / 60.0
    phase = satellite.model.mo + satellite.model.no_kozai * elapsed_minutes
    return math.floor(phase / (2.0 * math.pi))


def _ltdn_error_seconds(profile: SpacecraftProfile, ephemeris: Any) -> float:
    """Compare configured LTDN with the descending-node local solar time at orbit epoch."""
    epoch = profile.orbit.epoch_utc
    t = _timescale().from_datetime(epoch)
    sun_ra_deg = (
        ephemeris["earth"].at(t).observe(ephemeris["sun"]).apparent().radec()[0].degrees
    )
    descending_node_ra_deg = (profile.orbit.raan_deg + 180.0) % 360.0
    signed_offset_deg = (descending_node_ra_deg - sun_ra_deg + 180.0) % 360.0 - 180.0
    actual_hours = (12.0 + signed_offset_deg / 15.0) % 24.0
    expected_hour, expected_minute = (int(part) for part in profile.orbit.ltdn.split(":"))
    expected_hours = expected_hour + expected_minute / 60.0
    difference_hours = (actual_hours - expected_hours + 12.0) % 24.0 - 12.0
    return abs(difference_hours) * 3600.0


def generate_windows(
    cfg: ScenarioConfig,
    sources: list[Source],
    start_utc: datetime,
    end_utc: datetime,
) -> list[ObservationWindow]:
    """Generate refined geometric access windows and explicit rejection windows.

    Rejections are emitted for intervals in which the source is above the geometric horizon but
    pointing, daylight, or a spacecraft blackout prevents an acquisition. If a target is never
    geometrically visible during the requested interval, one ``NOT_VISIBLE`` record is emitted
    for that spacecraft/sensor/source combination.
    """
    start_utc = _ensure_utc(start_utc, "start_utc")
    end_utc = _ensure_utc(end_utc, "end_utc")
    if end_utc <= start_utc:
        raise ValueError("end_utc must be after start_utc")
    if not sources:
        return []

    step_s = cfg.window_search.coarse_step_s
    tolerance_s = cfg.window_search.refine_tolerance_s
    if step_s > 0.5 * min(
        sensor.exposure_seconds + min(sc.attitude.settle_seconds for sc in cfg.spacecraft.values())
        for sensor in cfg.sensors.values()
    ):
        raise ValueError("coarse orbit-search step exceeds half the minimum usable window")

    sample_times = _sample_datetimes(start_utc, end_utc, step_s)
    times = _timescale().from_datetimes(sample_times)
    ephemeris = load_ephemeris()
    earth, sun = ephemeris["earth"], ephemeris["sun"]
    output: list[ObservationWindow] = []

    for spacecraft_id in sorted(cfg.spacecraft):
        profile = cfg.spacecraft[spacecraft_id]
        ltdn_error_s = _ltdn_error_seconds(profile, ephemeris)
        if ltdn_error_s > _LTDN_TOLERANCE_S:
            raise ValueError(
                f"spacecraft {profile.id} RAAN implies LTDN differs from configured "
                f"{profile.orbit.ltdn} by {ltdn_error_s / 60.0:.2f} min "
                "(allowed ±2 min; ORB-02)"
            )
        satellite = build_satellite(profile)
        for sensor_id in profile.sensor_ids:
            sensor = cfg.sensors[sensor_id]
            for source in sorted(sources, key=lambda item: item.id):
                off, elevation, sun_elevation, _ = _geometry_series(
                    satellite, source, times, earth, sun
                )
                blackout_mask = np.fromiter(
                    (_in_blackout(profile, when) for when in sample_times),
                    dtype=bool,
                    count=len(sample_times),
                )
                states = [
                    _reason_for_state(
                        float(off[i]),
                        float(elevation[i]),
                        float(sun_elevation[i]),
                        profile.attitude.max_off_nadir_deg,
                        sensor.min_sun_elevation_deg,
                        bool(blackout_mask[i]),
                    )
                    for i in range(len(sample_times))
                ]
                visible_indices = [i for i, state in enumerate(states) if state is not None]
                if not visible_indices:
                    closest = float(np.min(off))
                    when = start_utc
                    oid = _window_id(profile.id, sensor.id, source.id, start_utc, 0)
                    output.append(
                        ObservationWindow(
                            id=oid,
                            spacecraft_id=profile.id,
                            sensor_id=sensor.id,
                            source_id=source.id,
                            start_utc=start_utc,
                            end_utc=end_utc,
                            pass_id=f"{profile.id}:unseen",
                            orbit_number=_orbit_number(satellite, when),
                            feasible=False,
                            rejection_reasons=(RejectionReason.NOT_VISIBLE,),
                            min_off_nadir_deg=closest,
                            options=(),
                            duration_s=sensor.exposure_seconds,
                            energy_wh=sensor.costs.energy_wh_per_scene,
                            data_bytes=sensor.costs.data_bytes_per_scene,
                        )
                    )
                    continue

                # Build runs of equal visibility/rejection state. Transitions are bisected so the
                # reported interval edges are more precise than the coarse discovery grid.
                run_bounds: list[tuple[int, int, tuple[RejectionReason, ...] | None]] = []
                run_start = 0
                run_state = states[0]
                for i in range(1, len(states)):
                    if states[i] != run_state:
                        run_bounds.append((run_start, i - 1, run_state))
                        run_start, run_state = i, states[i]
                run_bounds.append((run_start, len(states) - 1, run_state))

                window_index = 0
                for run_i, (first, last, state) in enumerate(run_bounds):
                    if state is None:
                        continue
                    left = sample_times[first]
                    right = sample_times[last]
                    if first > 0:
                        left = _refine_transition(
                            satellite,
                            source,
                            sample_times[first - 1],
                            sample_times[first],
                            state,
                            profile,
                            sensor,
                            earth,
                            sun,
                            tolerance_s,
                        )
                    if last < len(sample_times) - 1:
                        next_state = run_bounds[run_i + 1][2]
                        right = _refine_transition(
                            satellite,
                            source,
                            sample_times[last],
                            sample_times[last + 1],
                            next_state,
                            profile,
                            sensor,
                            earth,
                            sun,
                            tolerance_s,
                        )
                    midpoint = left + (right - left) / 2
                    orbit_number = _orbit_number(satellite, midpoint)
                    pass_id = f"{profile.id}:{orbit_number}"
                    output.append(
                        _make_window(
                            cfg,
                            profile,
                            sensor,
                            source,
                            satellite,
                            pass_id,
                            orbit_number,
                            left,
                            right,
                            state,
                            sample_times,
                            off,
                            first,
                            last,
                            earth,
                            sun,
                            tolerance_s,
                            window_index,
                        )
                    )
                    window_index += 1

    output.sort(
        key=lambda w: (
            w.start_utc,
            w.spacecraft_id,
            w.source_id,
            w.sensor_id,
            w.id,
        )
    )
    return output


def slew_time_s(
    prev: AcquisitionOption,
    nxt: AcquisitionOption,
    attitude: AttitudeConfig,
) -> float:
    """Return LOS-to-LOS slew time plus settle time, in seconds."""
    delta = math.acos(
        float(
            np.clip(
                np.dot(np.asarray(prev.los_unit_ecef), np.asarray(nxt.los_unit_ecef)),
                -1.0,
                1.0,
            )
        )
    )
    angle_deg = math.degrees(delta)
    return angle_deg / attitude.slew_rate_deg_s + attitude.settle_seconds


__all__ = ["build_satellite", "generate_windows", "load_ephemeris", "slew_time_s"]
