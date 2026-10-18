"""Refresh public catalogue/orbit context without changing a scientific run.

All external HTTP is opt-in through this command. The serving API only reads the local
snapshot. GP refreshes are cached for two hours; non-200 responses stop further fetching.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import math
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from aether.netpolicy import TIMEOUTS_S, assert_public_address, require_allowed_url
from aether.orbit import _timescale
from skyfield.api import EarthSatellite, wgs84

# PR-LIVE01: read-only context feed cadence, catalogue size, and response bound.
REFRESH_S = 7200
MAX_RESPONSE_BYTES = 1048576
DEFAULT_SNAPSHOT = Path(__file__).resolve().parents[1] / "data/live_context/latest.json"
FEEDS = {
    "celestrak": "https://celestrak.org/NORAD/elements/gp.php?NAME=LANDSAT&FORMAT=JSON",
    "emit": "https://cmr.earthdata.nasa.gov/search/granules.json?short_name=EMITL2BCH4PLM&version=002&page_size=5&sort_key=-start_date",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def fetch(url: str) -> bytes:
    parts = urlsplit(require_allowed_url(url))
    assert_public_address(parts.hostname)
    connection = http.client.HTTPSConnection(parts.hostname, timeout=TIMEOUTS_S[0])
    try:
        connection.connect()
        connection.sock.settimeout(TIMEOUTS_S[1])
        connection.request(
            "GET",
            parts.path + "?" + parts.query,
            headers={
                "Accept": "application/json",
                "User-Agent": "AETHER-public-research-demo/0.1",
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError(
                f"Provider HTTP {response.status}; no redirect or retry performed"
            )
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError("Provider response exceeds PR-LIVE01 byte limit")
        json.loads(data)
        return data
    finally:
        connection.close()


def refresh(path: Path) -> None:
    previous = json.loads(path.read_bytes()) if path.exists() else {"feeds": {}}
    feeds = dict(previous["feeds"])
    failure = None
    for name, url in FEEDS.items():
        cached = feeds.get(name)
        if (
            cached
            and (
                utcnow() - datetime.fromisoformat(cached["retrieved_at_utc"])
            ).total_seconds()
            < REFRESH_S
        ):
            continue
        try:
            raw = fetch(url)
            parsed = json.loads(raw)
            if name == "celestrak" and not isinstance(parsed, list):
                raise ValueError("Unexpected GP response shape")
            if name == "emit" and not isinstance(
                parsed.get("feed", {}).get("entry"), list
            ):
                raise ValueError("Unexpected CMR response shape")
            feeds[name] = {
                "source_url": url,
                "retrieved_at_utc": utcnow().isoformat(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "raw_json": raw.decode(),
            }
        except (
            OSError,
            http.client.HTTPException,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            failure = f"{name}: {type(exc).__name__}: {exc}"
            break  # Provider policy: stop; operator investigates before another attempt.
    payload = {
        "schema_version": 1,
        "last_attempt_utc": utcnow().isoformat(),
        "refresh_interval_s": REFRESH_S,
        "error": failure,
        "feeds": feeds,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    os.replace(temporary, path)
    if failure:
        raise RuntimeError(failure)


def context(path: Path) -> dict:
    """Hash-check cached provider bytes and propagate GP elements at the request UTC time."""
    now = utcnow()
    result = {
        "status": "unavailable",
        "computed_at_utc": now.isoformat(),
        "satellites": [],
        "granules": [],
        "feeds": [],
        "error": None,
    }
    if not path.exists():
        return result
    snapshot = json.loads(path.read_bytes())
    result["error"] = snapshot.get("error")
    for name, feed in snapshot["feeds"].items():
        if name not in FEEDS or feed["source_url"] != FEEDS[name]:
            raise ValueError("Unexpected provider URL in the context snapshot")
        raw = feed["raw_json"].encode()
        if hashlib.sha256(raw).hexdigest() != feed["sha256"]:
            raise ValueError(f"Cached {name} bytes do not match their recorded hash")
        age = (now - datetime.fromisoformat(feed["retrieved_at_utc"])).total_seconds()
        result["feeds"].append(
            {
                "id": name,
                "source_url": feed["source_url"],
                "retrieved_at_utc": feed["retrieved_at_utc"],
                "sha256": feed["sha256"],
                "age_s": age,
                "stale": age >= REFRESH_S,
            }
        )
        data = json.loads(raw)
        if name == "celestrak":
            ts = (
                _timescale()
            )  # Existing hash-verified local EOP; no network in propagation.
            for element in data:
                if element.get("OBJECT_NAME", "").replace(" ", "") not in {
                    "LANDSAT8",
                    "LANDSAT9",
                }:
                    continue
                row = {
                    "name": element["OBJECT_NAME"],
                    "norad_id": element["NORAD_CAT_ID"],
                    "epoch_utc": element["EPOCH"] + "Z",
                    "position_kind": "SGP4_PROPAGATED_ESTIMATE",
                    "latitude_deg": None,
                    "longitude_deg": None,
                    "altitude_km": None,
                    "error": None,
                }
                try:
                    satellite = EarthSatellite.from_omm(ts, element)
                    position = satellite.at(ts.from_datetime(now))
                    if position.message:
                        raise ValueError(str(position.message))
                    subpoint = wgs84.subpoint(position)
                    if not all(
                        math.isfinite(value)
                        for value in (
                            subpoint.latitude.degrees,
                            subpoint.longitude.degrees,
                            subpoint.elevation.km,
                        )
                    ):
                        raise ValueError("Non-finite propagated position")
                    row.update(
                        latitude_deg=float(subpoint.latitude.degrees),
                        longitude_deg=float(subpoint.longitude.degrees),
                        altitude_km=float(subpoint.elevation.km),
                    )
                except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
                    row["error"] = str(exc)
                result["satellites"].append(row)
        elif name == "emit":
            for item in data["feed"]["entry"]:
                result["granules"].append(
                    {
                        "id": item["id"],
                        "title": item["title"],
                        "observed_at_utc": item.get("time_start"),
                        "catalog_updated_at_utc": item.get("updated"),
                        "source_url": "https://cmr.earthdata.nasa.gov/search/concepts/"
                        + item["id"]
                        + ".html",
                    }
                )
    result["status"] = "available" if result["feeds"] else "unavailable"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument(
        "--watch", action="store_true", help="refresh no more often than every 2 h"
    )
    args = parser.parse_args()
    while True:
        refresh(args.output)
        print(json.dumps(context(args.output), indent=2), flush=True)
        if not args.watch:
            break
        time.sleep(REFRESH_S)


if __name__ == "__main__":
    main()
