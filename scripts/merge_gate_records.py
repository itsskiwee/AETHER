"""Merge G4.5 run-matrix records produced on several machines, then apply the stock gate rule.

    python scripts/merge_gate_records.py --into runs/g45-h168-merged \
        --from runs/g45-h168-diag --from <desktop>/runs/g45-h168-desktop \
        --families h168_long_horizon

Records are canonical JSON keyed by (family, policy, seed) with a machine-independent identity
(config hashes, aether code SHA-256, runtime input hashes and package versions), so two honest
copies of one run are byte-identical. A differing copy stops the merge: it means the machines did
not reproduce each other, which is a finding to report, not a conflict to resolve by choosing one.

The verdict comes from ``aether.evaluation.gate.run_gate`` with a run function that refuses to
compute. A missing record, or one whose identity does not match this checkout, raises instead of
being recomputed. Run this at the commit whose ``backend/aether`` produced the records.

A family with every tuning seed gets the registered verdict (``seed_subset_only: false``). A family
with only some seeds is reported as a subset diagnostic over the seeds present, never a verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from aether.evaluation.gate import REFERENCE, run_gate
from aether.evaluation.protocol import load_protocol, read_seeds

REPO = Path(__file__).resolve().parents[1]


class MissingRecordError(RuntimeError):
    pass


def _refuse(bundle, policy, seed):
    raise MissingRecordError(
        f"no reusable record for {policy.value}/{seed}: missing, or its "
        "identity does not match this checkout; refusing to recompute"
    )


def merge(into: Path, sources: list[Path]) -> dict:
    copied, identical, origin = 0, 0, {}
    for src in sources:
        for path in sorted((src / "records").rglob("*.json")):
            rel = path.relative_to(src)
            dest = into / rel
            data = path.read_bytes()
            if dest.exists():
                if dest.read_bytes() != data:
                    raise RuntimeError(
                        f"cross-machine mismatch for {rel.as_posix()}: {src} differs from "
                        f"{origin.get(rel.as_posix(), into)}"
                    )
                identical += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
            origin[rel.as_posix()] = str(src)
            copied += 1
    return {"copied": copied, "identical_duplicates": identical, "origin": origin}


def seeds_present(into: Path, family: str) -> list[int]:
    per_policy = [
        {int(p.stem) for p in (into / "records" / family / policy).glob("*.json")}
        for policy in REFERENCE
    ]
    return sorted(set.intersection(*per_policy))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--into", type=Path, required=True)
    ap.add_argument("--from", dest="sources", type=Path, action="append", required=True)
    ap.add_argument("--families", required=True, help="comma-separated")
    args = ap.parse_args()
    into = args.into.resolve()
    into.mkdir(parents=True, exist_ok=True)
    summary = merge(into, [s.resolve() for s in args.sources])

    proto = load_protocol(REPO / "experiments/protocol.yaml")
    tuning = read_seeds(REPO / proto.tuning_seeds)
    report = {
        "merge": {k: v for k, v in summary.items() if k != "origin"},
        "families": {},
    }
    for family in [f for f in args.families.split(",") if f]:
        present = [s for s in seeds_present(into, family) if s in tuning]
        if not present:
            report["families"][family] = {"status": "NO_RECORDS"}
            continue
        complete = set(present) == set(tuning)
        out = into / family
        gate = run_gate(
            REPO,
            into,
            [family],
            workers=1,
            seed_subset=None if complete else tuple(present),
            run_fn=_refuse,
        )
        (into / "gate.json").replace(out.with_suffix(".gate.json"))
        (into / "gate-seeds.csv").replace(out.with_suffix(".gate-seeds.csv"))
        v = gate["per_family"][family]
        report["families"][family] = {
            "status": "VERDICT" if complete else "SUBSET_DIAGNOSTIC_NOT_A_VERDICT",
            "n_seeds": len(present),
            "passed": v["passed"],
            "gap_mean_random_minus_oracle": v["gap_mean_random_minus_oracle"],
            "threshold_2sd": v["threshold_2sd"],
            "reference_checker_violations": v["reference_checker_violations"],
        }
    sha = hashlib.sha256()
    for path in sorted((into / "records").rglob("*.json")):
        sha.update(
            path.relative_to(into).as_posix().encode() + b"\0" + path.read_bytes()
        )
    report["records_sha256"] = sha.hexdigest()
    report["sources"] = [str(s) for s in args.sources]
    (into / "merge-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
