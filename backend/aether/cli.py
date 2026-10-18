"""Command-line entry point (PRD 22.2). Lane L1 owns this file.

    python -m aether.cli validate --config configs/demo.yaml [--family configs/scenarios/m2_*.yaml]
    python -m aether.cli windows  --config ... --output runs/windows.json
    python -m aether.cli simulate --config ... --policies largest_first,adaptive_eig --seed 1000
    python -m aether.cli benchmark --protocol experiments/protocol.yaml \
        --seeds experiments/seeds_dev.txt
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import zipfile
from datetime import timedelta
from pathlib import Path

from aether.config import load_scenario


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _packages() -> dict[str, str]:
    names = (
        "aether",
        "numpy",
        "scipy",
        "pydantic",
        "pyyaml",
        "sgp4",
        "skyfield",
        "ortools",
        "astropy",
        "pyproj",
        "shapely",
        "fastapi",
        "uvicorn",
    )
    return {name: version for name in names if (version := _package_version(name)) is not None}


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _manifest(bundle, config_paths: list[Path], input_paths: list[Path]) -> dict:
    return {
        "model_config_hash": bundle.model.config_hash(),
        "truth_config_hash": bundle.truth.config_hash(),
        "config_inputs_sha256": {
            str(path): _sha256(path) for path in sorted(set(config_paths)) if path.is_file()
        },
        "input_sha256": {
            str(path): _sha256(path) for path in sorted(set(input_paths)) if path.is_file()
        },
        "code_version": __import__("aether").__version__,
        "package_versions": _packages(),
    }


def _config_paths(config: Path, family: Path | None = None) -> list[Path]:
    """Resolve the local YAML files that define a scenario, including one-level extends."""
    import yaml

    files = [config.resolve()]
    if family is not None:
        files.append(family.resolve())
    raw = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    if raw.get("extends"):
        files.append((config.parent / raw["extends"]).resolve())
        raw = yaml.safe_load(files[-1].read_text(encoding="utf-8")) or {}
    for key in ("region_file", "spacecraft_files", "sensor_files"):
        value = raw.get(key, [])
        for entry in [value] if isinstance(value, str) else value:
            files.append((config.parent / entry).resolve())
    return files


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


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


def _windows(args: argparse.Namespace) -> int:
    from aether.orbit import generate_windows
    from aether.simulation.runner import generate_sources

    bundle = load_scenario(args.config, args.family, seed=args.seed)
    cfg = bundle.model
    start = cfg.simulation_epoch_utc
    end = start + timedelta(hours=cfg.horizon_hours)
    sources = generate_sources(cfg, cfg.random_seed)
    windows = generate_windows(cfg, list(sources), start, end)
    payload = {
        "scenario_id": cfg.scenario_id,
        "seed": cfg.random_seed,
        "sources": [source.model_dump(mode="json") for source in sources],
        "windows": [window.model_dump(mode="json") for window in windows],
    }
    _write_json(Path(args.output), payload)
    return 0


def _simulate(args: argparse.Namespace) -> int:
    from aether.contracts.enums import PolicyId
    from aether.simulation.runner import run_policy

    config = Path(args.config).resolve()
    bundle = load_scenario(config, args.family, seed=args.seed)
    output_dir = Path(args.output_dir)
    root = _repo_root()
    inputs = [
        root / "data/ephemeris/de421.bsp",
        root / "data/ephemeris/manifest.json",
        root / "data/eop/finals2000A.all",
        root / "data/eop/manifest.json",
    ]
    for name in args.policies.split(","):
        policy = PolicyId(name.strip())
        print(f"Simulating {policy.value}, seed {bundle.model.random_seed}…", flush=True)
        run = run_policy(bundle, policy, bundle.model.random_seed)
        run_dir = output_dir / run.run_id
        _write_json(run_dir / "run.json", run.model_dump(mode="json"))
        family = Path(args.family).resolve() if args.family else None
        _write_json(
            run_dir / "manifest.json", _manifest(bundle, _config_paths(config, family), inputs)
        )
        print(f"Wrote {run_dir / 'run.json'}", flush=True)
    return 0


def _benchmark(args: argparse.Namespace) -> int:
    from aether.evaluation.benchmark import benchmark

    benchmark(args.protocol, args.seeds, args.output_dir)
    return 0


def _export(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir) / args.run_id
    record_path = run_dir / "run.json"
    manifest_path = run_dir / "manifest.json"
    if not record_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f"run or manifest missing under {run_dir}")
    from aether.contracts.models import RunRecord

    record = RunRecord.model_validate_json(record_path.read_text(encoding="utf-8"))
    # Loading through the contract is part of export validation; archive canonical record bytes.
    record_bytes = (
        json.dumps(
            record.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["run_json_sha256"] = hashlib.sha256(record_bytes).hexdigest()
    manifest["run_id"] = record.run_id
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("run.json", record_bytes)
        archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aether")
    sub = parser.add_subparsers(dest="command", required=True)
    p_val = sub.add_parser("validate", help="load and validate a scenario config")
    p_val.add_argument("--config", required=True)
    p_val.add_argument("--family", default=None)
    p_val.set_defaults(func=_validate)
    p = sub.add_parser("windows", help="generate offline orbit windows")
    p.add_argument("--config", required=True)
    p.add_argument("--family")
    p.add_argument("--seed", type=int)
    p.add_argument("--output", required=True)
    p.set_defaults(func=_windows)
    p = sub.add_parser("simulate", help="run one or more closed-loop policies")
    p.add_argument("--config", required=True)
    p.add_argument("--family")
    p.add_argument("--seed", type=int)
    p.add_argument("--policies", default="largest_first,adaptive_eig")
    p.add_argument("--output-dir", default="runs")
    p.set_defaults(func=_simulate)
    p = sub.add_parser("benchmark", help="run the configured tuning-seed benchmark")
    p.add_argument("--protocol", required=True)
    p.add_argument("--seeds", required=True)
    p.add_argument("--output-dir", required=True)
    p.set_defaults(func=_benchmark)
    p = sub.add_parser("export", help="validate and package a run artifact")
    p.add_argument("--run-dir", default="runs")
    p.add_argument("--run-id", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=_export)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
