"""One-time, policy-checked fetch utility for the pinned JPL DE421 input."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from aether.netpolicy import TIMEOUTS_S, assert_public_address, require_allowed_url

URL = "https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de421.bsp"
ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "data" / "ephemeris" / "de421.bsp"
MANIFEST = ROOT / "data" / "ephemeris" / "manifest.json"
CHUNK_BYTES = 1024 * 1024


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_existing() -> bool:
    if not TARGET.is_file() or not MANIFEST.is_file():
        return False
    record = json.loads(MANIFEST.read_text(encoding="utf-8"))
    valid = (
        record.get("filename") == TARGET.name
        and record.get("url") == URL
        and record.get("byte_size") == TARGET.stat().st_size
        and record.get("sha256") == _file_sha256(TARGET)
    )
    if not valid:
        raise ValueError("existing DE421 file does not match its manifest; use --force to refresh")
    return True


def fetch_ephemeris(*, force: bool = False) -> Path:
    """Fetch DE421 only from the allowlisted public JPL host, then atomically pin its hash."""
    if not force and _check_existing():
        print(f"verified existing {TARGET} ({_file_sha256(TARGET)})")
        return TARGET
    require_allowed_url(URL)
    parts = urlsplit(URL)
    assert_public_address(parts.hostname or "")

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    connection = http.client.HTTPSConnection(parts.hostname, timeout=TIMEOUTS_S[0])
    temporary_path: Path | None = None
    manifest_temporary: Path | None = None
    try:
        connection.connect()
        if connection.sock is not None:
            connection.sock.settimeout(TIMEOUTS_S[1])
        request_path = parts.path + (f"?{parts.query}" if parts.query else "")
        connection.request("GET", request_path, headers={"User-Agent": "AETHER pinned-input fetch"})
        response = connection.getresponse()
        if response.status != 200:
            raise OSError(f"DE421 server returned HTTP {response.status}")
        digest = hashlib.sha256()
        byte_size = 0
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=TARGET.parent, prefix=".de421-", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            while block := response.read(CHUNK_BYTES):
                temporary.write(block)
                digest.update(block)
                byte_size += len(block)
        sha256 = digest.hexdigest()
        manifest_record = {
            "filename": TARGET.name,
            "url": URL,
            "byte_size": byte_size,
            "sha256": sha256,
            "retrieved_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=MANIFEST.parent,
            prefix=".de421-manifest-",
            delete=False,
        ) as temporary:
            manifest_temporary = Path(temporary.name)
            json.dump(manifest_record, temporary, indent=2)
            temporary.write("\n")
        os.replace(temporary_path, TARGET)
        temporary_path = None
        os.replace(manifest_temporary, MANIFEST)
        manifest_temporary = None
        print(f"fetched {TARGET} ({byte_size} bytes, sha256 {sha256})")
        return TARGET
    finally:
        connection.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        if manifest_temporary is not None:
            manifest_temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="fetch and replace the local pin")
    fetch_ephemeris(force=parser.parse_args().force)


if __name__ == "__main__":
    main()
