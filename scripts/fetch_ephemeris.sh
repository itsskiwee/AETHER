#!/usr/bin/env bash
set -euo pipefail

readonly url="https://ssd.jpl.nasa.gov/ftp/eph/planets/bsp/de421.bsp"
readonly root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly directory="$root/data/ephemeris"
readonly file="$directory/de421.bsp"
readonly manifest="$directory/manifest.json"

mkdir -p "$directory"

if [[ -e "$file" || -e "$manifest" ]]; then
    if [[ ! -f "$file" || ! -f "$manifest" ]]; then
        echo "DE421 file and first-fetch manifest must either both exist or both be absent" >&2
        exit 1
    fi
    python3 - "$file" "$manifest" "$url" <<'PY'
import hashlib
import json
import pathlib
import sys

file_path, manifest_path = map(pathlib.Path, sys.argv[1:3])
expected_url = sys.argv[3]
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
digest = hashlib.sha256()
with file_path.open("rb") as stream:
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
if manifest.get("url") != expected_url:
    raise SystemExit("DE421 manifest URL does not match the registered JPL source")
if manifest.get("byte_size") != file_path.stat().st_size:
    raise SystemExit("DE421 byte size does not match its first-fetch manifest")
if manifest.get("sha256") != digest.hexdigest():
    raise SystemExit("DE421 SHA-256 mismatch; refusing to replace the first-fetch pin")
print("Verified existing first-fetch DE421 pin")
PY
    exit 0
fi

temporary_file="$(mktemp "$directory/.de421.bsp.XXXXXX")"
temporary_manifest="$(mktemp "$directory/.manifest.json.XXXXXX")"
cleanup() {
    rm -f "$temporary_file" "$temporary_manifest"
}
trap cleanup EXIT

curl --fail --location --retry 3 --output "$temporary_file" "$url"
python3 - "$temporary_file" "$temporary_manifest" "$url" <<'PY'
from datetime import UTC, datetime
import hashlib
import json
import pathlib
import sys

file_path, manifest_path = map(pathlib.Path, sys.argv[1:3])
url = sys.argv[3]
manifest = {
    "filename": "de421.bsp",
    "url": url,
    "byte_size": file_path.stat().st_size,
    "sha256": hashlib.sha256(file_path.read_bytes()).hexdigest(),
    "retrieved_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
}
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY
mv "$temporary_file" "$file"
mv "$temporary_manifest" "$manifest"
trap - EXIT
echo "Pinned JPL DE421 at $file"
