"""Package an exact committed source revision and accepted pinned-data demo for replay.

This is a demo delivery archive, not scientific gate or release certification. Reads existing
artifacts without running simulations; excludes unfinished benchmarks, caches and credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--demo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, demo, output = (
        args.source.resolve(),
        args.demo.resolve(),
        args.output.resolve(),
    )
    if output.exists():
        raise SystemExit(f"Refusing to overwrite {output}")
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=source, text=True
    ).strip()
    source_zip = subprocess.check_output(
        ["git", "archive", "--format=zip", revision], cwd=source
    )
    with zipfile.ZipFile(io.BytesIO(source_zip)) as committed:
        files = {
            item.filename: committed.read(item)
            for item in committed.infolist()
            if not item.is_dir()
        }
    acceptance = json.loads((demo / "acceptance.json").read_bytes())
    summaries = {row["policy"]: row for row in acceptance["runs"]}
    if set(summaries) != {"adaptive_eig", "largest_first"}:
        raise ValueError("Acceptance must contain the two demo policies")
    found = set()
    for path in sorted(demo.glob("*/run.json")):
        record_bytes = path.read_bytes()
        run = json.loads(record_bytes)
        summary = summaries[run["policy_id"]]
        canonical = (
            json.dumps(
                run,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode()
        # verify_demo names this field canonical_json_sha256 but hashes the saved file bytes.
        if digest(record_bytes) != summary["canonical_json_sha256"]:
            raise ValueError(f"Acceptance hash mismatch: {path}")
        if not summary["replay_identical"] or not summary["export_reload_verified"]:
            raise ValueError("Replay/export acceptance is incomplete")
        if (
            summary["checker_violations"] != 0
            or not run["validations"]
            or len(run["validations"]) != len(run["plans"])
            or any(not v["ok"] or v["violations"] for v in run["validations"])
        ):
            raise ValueError(f"Schedule acceptance failed: {path}")
        ref = run["input_dataset"]
        manifest_bytes = files[ref["manifest_path"]]
        if digest(manifest_bytes) != ref["manifest_sha256"]:
            raise ValueError("Committed source does not contain this run's dataset")
        dataset = json.loads(manifest_bytes)
        for entry in [dataset["normalized"], *dataset["raw_files"]]:
            data = files[entry["path"]]
            if digest(data) != entry["sha256"]:
                raise ValueError(f"Pinned input mismatch: {entry['path']}")
        for name in ("run.json", "manifest.json", "performance.json"):
            artifact = path.parent / name
            files[f"runs/demo-pinned/{path.parent.name}/{name}"] = artifact.read_bytes()
        export = demo / f"{path.parent.name}.zip"
        export_bytes = export.read_bytes()
        with zipfile.ZipFile(io.BytesIO(export_bytes)) as exported:
            if digest(exported.read("run.json")) != digest(canonical):
                raise ValueError(f"Export record mismatch: {export}")
        files[f"runs/demo-pinned/{export.name}"] = export_bytes
        found.add(run["policy_id"])
    if found != set(summaries):
        raise ValueError("Both accepted demo runs must exist")
    files["runs/demo-pinned/acceptance.json"] = (demo / "acceptance.json").read_bytes()
    guide = f"""# AETHER: pinned-data replay bundle

Source revision: `{revision}`. Source files are from that exact Git commit. Uncommitted
working-tree edits and incomplete experiment jobs are excluded. No dependencies are bundled.

## Start the product

Use Python 3.12 or newer and Node.js/npm. From the extracted project folder:

```bash
python -m venv backend/.venv
backend/.venv/bin/pip install -e './backend[dev,geo,api]'
npm --prefix frontend ci
bash scripts/serve-demo.sh runs/demo-pinned
```

Open http://127.0.0.1:4173. Initial dependency installation needs network access;
the saved demo then replays offline. Do not regenerate the simulation to view it.
Comparison benchmark outputs are excluded while their generation is unfinished;
an unavailable comparison is not a scientific verdict.

## What this demonstrates

Twenty real historical EMIT records provide locations for twenty simulated source
hypotheses, with zero uniform-fill locations. Both policies use 1,494 windows.
Adaptive: 47 checked plans, 51 acquisitions. Largest-first: 41 checked plans,
37 acquisitions. Both have zero recorded checker violations, byte-identical replay
and verified exports in the included acceptance record. The API exposes source
lineage, historical records, run input hashes and separately measured timing.

The spacecraft, weather, acquisitions and ground truth are simulated. Historical
rates do not establish present activity. Null rates and unknown retrieval time are
preserved. The hour-20 forecast refresh changes no selected option in these runs.

## Scientific limits

This bundle certifies no policy advantage or completed research acceptance.
Pinned-scenario capacity fails its per-pass threshold (one pass has two rather
than four acquisitions). The synthetic discriminability pilot failed. The protocol
is unlocked; no holdout result is claimed. Check the ongoing integration reports
for later scientific results; this is a fixed demonstration snapshot.

ARCHIVE_CONTENTS.json lists SHA-256 hashes for every other file in this bundle.
"""
    files["START_HERE.md"] = guide.encode()
    index = {
        "source_revision": revision,
        "scope": "pinned-data demonstration replay",
        "scientific_acceptance_complete": False,
        "files": {
            name: {"sha256": digest(data), "size_bytes": len(data)}
            for name, data in sorted(files.items())
        },
    }
    files["ARCHIVE_CONTENTS.json"] = (
        json.dumps(index, sort_keys=True, indent=2) + "\n"
    ).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(f"AETHER/{name}", data)
    checksum = digest(output.read_bytes())
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{checksum}  {output.name}\n"
    )
    print(
        json.dumps(
            {
                "archive": str(output),
                "sha256": checksum,
                "source_revision": revision,
                "files": len(files),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
