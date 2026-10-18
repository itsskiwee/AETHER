"""Copy only accepted demo artifacts into the small repository-hosted replay sample."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", type=Path, required=True)
    parser.add_argument(
        "--destination", type=Path, default=Path("data/fixtures/hosted_replay")
    )
    args = parser.parse_args()
    if args.destination.exists():
        raise SystemExit(f"Refusing to overwrite {args.destination}")
    acceptance = json.loads((args.demo / "acceptance.json").read_bytes())
    rows = {row["policy"]: row for row in acceptance["runs"]}
    paths = sorted(args.demo.glob("*/run.json"))
    if len(paths) != 2 or set(rows) != {"adaptive_eig", "largest_first"}:
        raise ValueError("Expected the accepted two-policy demo")
    planned: dict[str, bytes] = {
        "acceptance.json": (args.demo / "acceptance.json").read_bytes()
    }
    found = set()
    for path in paths:
        data = path.read_bytes()
        run = json.loads(data)
        row = rows[run["policy_id"]]
        if hashlib.sha256(data).hexdigest() != row["canonical_json_sha256"]:
            raise ValueError(f"Acceptance hash mismatch: {path}")
        if (
            row["checker_violations"] != 0
            or not row["replay_identical"]
            or not row["export_reload_verified"]
            or not run.get("input_dataset")
        ):
            raise ValueError(f"Demo acceptance incomplete: {path}")
        if len(run["plans"]) != len(run["validations"]) or any(
            not item["ok"] or item["violations"] for item in run["validations"]
        ):
            raise ValueError(f"Invalid schedule: {path}")
        for name in ("run.json", "manifest.json", "performance.json"):
            planned[f"{path.parent.name}/{name}"] = (path.parent / name).read_bytes()
        found.add(run["policy_id"])
    if found != set(rows):
        raise ValueError("Duplicate or missing demo policy")
    planned["README.md"] = (
        b"# Recorded pinned-data demonstration\n\n"
        b"These are saved simulated mission records, not live satellite observations.\n"
        b"Twenty real historical EMIT records supply source locations only.\n"
        b"Source sample hashes and missing provenance are preserved in the run manifests.\n"
        b"Both records have byte-identical replay and verified exports in acceptance.json.\n"
        b"The forecast refresh changes no selection in this sample. No policy advantage,\n"
        b"completed holdout experiment or passed capacity gate is claimed.\n"
        b"Comparison artifacts are omitted until their development run is finished.\n"
    )
    hashes = {
        name: hashlib.sha256(data).hexdigest() for name, data in sorted(planned.items())
    }
    planned["sha256.json"] = (
        json.dumps(hashes, sort_keys=True, indent=2) + "\n"
    ).encode()
    try:
        args.destination.mkdir(parents=True)
        for name, data in planned.items():
            target = args.destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    except Exception:
        shutil.rmtree(args.destination, ignore_errors=True)
        raise
    print(f"Prepared {len(paths)} accepted replay records in {args.destination}")


if __name__ == "__main__":
    main()
