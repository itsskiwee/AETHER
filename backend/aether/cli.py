"""Command-line entry point (PRD 22.2). Lane L1 owns this file.

    python -m aether.cli validate --config configs/demo.yaml [--family configs/scenarios/m2_*.yaml]
    python -m aether.cli windows  --config ... --output runs/windows.json
    python -m aether.cli simulate --config ... --policies largest_first,adaptive_eig --seed 1000
    python -m aether.cli benchmark --protocol experiments/protocol.yaml \
        --seeds experiments/seeds_dev.txt
"""

from __future__ import annotations

import argparse
import json
import sys

from aether.config import load_scenario


def _validate(args: argparse.Namespace) -> int:
    bundle = load_scenario(args.config, args.family)
    cfg = bundle.model
    summary = {
        "scenario_id": cfg.scenario_id,
        "family": cfg.family,
        "model_config_hash": cfg.config_hash(),
        "truth_config_hash": bundle.truth.config_hash(),
        "misspecified": cfg.config_hash() != bundle.truth.config_hash(),
        "spacecraft": sorted(cfg.spacecraft),
        "sensors": sorted(cfg.sensors),
        "regimes": {
            r.name.value: {
                "weight": r.weight,
                "stationary_p_active": round(r.stationary_p_active, 4),
                "correlation_time_h": round(r.correlation_time_hours, 2),
            }
            for r in cfg.sources.regimes
        },
    }
    json.dump(summary, sys.stdout, indent=2)
    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aether")
    sub = parser.add_subparsers(dest="command", required=True)
    p_val = sub.add_parser("validate", help="load and validate a scenario config")
    p_val.add_argument("--config", required=True)
    p_val.add_argument("--family", default=None)
    p_val.set_defaults(func=_validate)
    for name in ("windows", "simulate", "benchmark", "export"):
        p = sub.add_parser(name, help=f"{name} (not implemented yet, see Work_Plan.md)")
        p.set_defaults(func=lambda a, n=name: sys.exit(f"'{n}' not implemented yet"))
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
