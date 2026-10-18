"""Command-line entry point (PRD 22.2). Lane L1 owns this file.

    python -m aether.cli validate --config configs/demo.yaml [--family configs/scenarios/m2_*.yaml]
    python -m aether.cli windows  --config ... --output runs/windows.json
    python -m aether.cli simulate --config ... --policies largest_first,adaptive_eig --seed 1000

``simulate`` writes ``run.json`` (deterministic bytes), ``manifest.json`` and
``performance.json`` (measured wall times; machine-dependent, never part of the RunRecord).

``windows``, ``simulate`` and ``benchmark`` place sources from the config's pinned plume dataset
(``sources.plume_dataset``, docs/dataset-interface.md) through ``runner.resolve_sources``.
``--synthetic-only`` is the explicit uniform-placement mode; it changes the config hash. A named
dataset that is missing or altered is an error, never a silent fallback.
    python -m aether.cli benchmark --protocol experiments/protocol.yaml \
        --seeds experiments/seeds_dev.txt --output-dir runs/benchmark [--synthetic-only]
    python -m aether.cli export --run-dir runs --run-id <id> --output runs/<id>.zip
    python -m aether.cli verify-export --archive runs/<id>.zip

Run manifests carry input lineage (``lineage_version`` 1): every path is repo-relative POSIX, and
``input_sha256`` lists the pinned ephemeris/EOP files plus, when a dataset is configured, the
dataset manifest, its normalized records and every selected raw file. ``export`` re-verifies that
lineage against the record and the repository bytes and refuses missing or altered evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import zipfile
from datetime import timedelta
from pathlib import Path, PurePosixPath

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


LINEAGE_VERSION = 1
# Result-affecting pinned inputs every run reads (orbit frames and Earth orientation).
PINNED_INPUTS = (
    "data/ephemeris/de421.bsp",
    "data/ephemeris/manifest.json",
    "data/eop/finals2000A.all",
    "data/eop/manifest.json",
)


class LineageError(ValueError):
    """A run manifest's input lineage is missing, non-portable or differs from the inputs."""


def _repo_relative(path: Path) -> str:
    """Repo-relative POSIX form of ``path``; inputs outside the repository are refused."""
    root = _repo_root().resolve()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise LineageError(f"input {path} is outside the repository {root}") from exc


def _portable_key(key: str) -> str:
    pure = PurePosixPath(key)
    if not key or "\\" in key or pure.is_absolute() or ".." in pure.parts:
        raise LineageError(f"lineage path {key!r} is not a repo-relative POSIX path")
    return key


def _dataset_lineage(bundle) -> tuple[dict | None, list[str]]:
    """The configured dataset's identity and the repo-relative files it consists of.

    Reads the dataset manifest only after the runner's loader has verified it, so every listed
    path and hash here is the one the run used.
    """
    spec = bundle.model.sources.plume_dataset
    if spec is None:
        return None, []
    from aether.simulation.runner import load_configured_dataset

    dataset = load_configured_dataset(bundle.model)
    manifest = json.loads((_repo_root() / spec.manifest).read_bytes())
    normalized = manifest["normalized"]["path"]
    raw = [record["path"] for record in manifest["raw_files"]]
    identity = {
        "dataset_id": dataset.dataset_id,
        "manifest_path": spec.manifest,
        "manifest_sha256": dataset.manifest_sha256,
        "normalized_path": normalized,
        "normalized_sha256": dataset.normalized_sha256,
        "raw_file_count": len(raw),
        "adapter_version": manifest.get("adapter_version"),
        "transformation_version": manifest.get("transformation_version"),
        "retrieval_status": manifest.get("retrieval", {}).get("status"),
    }
    return identity, [spec.manifest, normalized, *raw]


def _dataset_inputs(bundle) -> list[Path]:
    """Every file of the configured dataset: manifest, normalized records, selected raw files."""
    return [_repo_root() / rel for rel in _dataset_lineage(bundle)[1]]


def _manifest(
    bundle, config_paths: list[Path], input_paths: list[Path], *, synthetic_only: bool = False
) -> dict:
    from aether.evaluation.matrix import code_sha256

    spec = bundle.model.sources.plume_dataset
    dataset, _ = _dataset_lineage(bundle)
    missing = [path for path in input_paths if not path.is_file()]
    if missing:
        raise LineageError(f"required run inputs are missing: {[str(p) for p in missing]}")
    return {
        "lineage_version": LINEAGE_VERSION,
        "synthetic_only": synthetic_only,
        "plume_dataset": None if spec is None else spec.model_dump(mode="json"),
        "input_dataset": dataset,
        "model_config_hash": bundle.model.config_hash(),
        "truth_config_hash": bundle.truth.config_hash(),
        "config_inputs_sha256": {
            _config_key(path): _sha256(path) for path in sorted(set(config_paths)) if path.is_file()
        },
        "input_sha256": {_repo_relative(path): _sha256(path) for path in sorted(set(input_paths))},
        "code_version": __import__("aether").__version__,
        "code_sha256": code_sha256(),
        "package_versions": _packages(),
    }


def _config_key(path: Path) -> str:
    """Repo-relative for configs in the repository; ad-hoc configs elsewhere keep their name only.

    Config bytes are already bound by ``model_config_hash``; this map is human-readable lineage.
    """
    try:
        return _repo_relative(path)
    except LineageError:
        return f"external:{path.name}"


def verify_lineage(manifest: dict, record, *, root: Path | None = None) -> dict:
    """Check a run manifest's lineage against its RunRecord and the repository bytes.

    Raises ``LineageError`` when a required entry is missing, a path is not portable, the dataset
    identity disagrees with ``record.input_dataset``, or a listed file is missing or altered.
    Returns a summary of what was verified.
    """
    root = (root or _repo_root()).resolve()
    if manifest.get("lineage_version") != LINEAGE_VERSION:
        raise LineageError("run manifest has no lineage_version 1 input lineage")
    for key in ("model_config_hash", "truth_config_hash"):
        if manifest.get(key) != getattr(record, key):
            raise LineageError(f"manifest {key} differs from the run record")
    inputs = manifest.get("input_sha256")
    if not isinstance(inputs, dict):
        raise LineageError("manifest input_sha256 must be an object")
    for key in inputs:
        _portable_key(key)
    required = dict.fromkeys(PINNED_INPUTS)
    ref = record.input_dataset
    spec = manifest.get("plume_dataset")
    if ref is None:
        if spec is not None or manifest.get("input_dataset") is not None:
            raise LineageError("manifest names a plume dataset but the run record has none")
    else:
        if not isinstance(spec, dict) or (spec.get("manifest"), spec.get("manifest_sha256")) != (
            ref.manifest_path,
            ref.manifest_sha256,
        ):
            raise LineageError("manifest plume_dataset differs from run.input_dataset")
        dataset_file = root / _portable_key(ref.manifest_path)
        if not dataset_file.is_file():
            raise LineageError(f"dataset manifest {ref.manifest_path} is missing")
        if _sha256(dataset_file) != ref.manifest_sha256:
            raise LineageError(f"dataset manifest {ref.manifest_path} was altered")
        dataset = json.loads(dataset_file.read_bytes())
        if dataset.get("dataset_id") != ref.dataset_id:
            raise LineageError("dataset manifest dataset_id differs from run.input_dataset")
        normalized = dataset["normalized"]
        if normalized["sha256"] != ref.normalized_sha256:
            raise LineageError("normalized dataset hash differs from run.input_dataset")
        identity = manifest.get("input_dataset") or {}
        if (identity.get("manifest_path"), identity.get("normalized_path")) != (
            ref.manifest_path,
            normalized["path"],
        ):
            raise LineageError("manifest input_dataset paths differ from the dataset manifest")
        required[ref.manifest_path] = ref.manifest_sha256
        required[normalized["path"]] = normalized["sha256"]
        for raw in dataset["raw_files"]:
            required[raw["path"]] = raw["sha256"]
    absent = sorted(path for path in required if path not in inputs)
    if absent:
        raise LineageError(f"input_sha256 lacks required evidence: {absent[:5]}")
    for path, expected in required.items():
        if expected is not None and inputs[path] != expected:
            raise LineageError(f"input_sha256[{path!r}] differs from the dataset manifest")
    for path, digest in sorted(inputs.items()):
        target = (root / path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise LineageError(f"listed input {path} is missing")
        if _sha256(target) != digest:
            raise LineageError(f"listed input {path} was altered since the run")
    return {
        "verified_input_files": len(inputs),
        "dataset_files": len(required) - len(PINNED_INPUTS),
        "input_dataset": None if ref is None else ref.dataset_id,
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
    from aether.simulation.runner import resolve_sources

    bundle = load_scenario(
        args.config, args.family, seed=args.seed, synthetic_only=args.synthetic_only
    )
    cfg = bundle.model
    start = cfg.simulation_epoch_utc
    end = start + timedelta(hours=cfg.horizon_hours)
    sources, dataset_ref = resolve_sources(cfg, cfg.random_seed)
    windows = generate_windows(cfg, list(sources), start, end)
    payload = {
        "scenario_id": cfg.scenario_id,
        "seed": cfg.random_seed,
        "model_config_hash": cfg.config_hash(),
        "input_dataset": None if dataset_ref is None else dataset_ref.model_dump(mode="json"),
        "sources": [source.model_dump(mode="json") for source in sources],
        "windows": [window.model_dump(mode="json") for window in windows],
    }
    _write_json(Path(args.output), payload)
    return 0


def _simulate(args: argparse.Namespace) -> int:
    from aether.contracts.enums import PolicyId
    from aether.simulation.runner import run_policy_with_performance

    config = Path(args.config).resolve()
    bundle = load_scenario(config, args.family, seed=args.seed, synthetic_only=args.synthetic_only)
    output_dir = Path(args.output_dir)
    root = _repo_root()
    inputs = [root / rel for rel in PINNED_INPUTS] + _dataset_inputs(bundle)
    for name in args.policies.split(","):
        policy = PolicyId(name.strip())
        print(f"Simulating {policy.value}, seed {bundle.model.random_seed}…", flush=True)
        run, performance = run_policy_with_performance(bundle, policy, bundle.model.random_seed)
        run_dir = output_dir / run.run_id
        _write_json(run_dir / "run.json", run.model_dump(mode="json"))
        # Measured wall times live beside the deterministic record, never inside it (PERF-01).
        _write_json(run_dir / "performance.json", performance.model_dump(mode="json"))
        family = Path(args.family).resolve() if args.family else None
        manifest = _manifest(
            bundle, _config_paths(config, family), inputs, synthetic_only=args.synthetic_only
        )
        verify_lineage(manifest, run)  # fail at the producer, not first at export
        _write_json(run_dir / "manifest.json", manifest)
        print(f"Wrote {run_dir / 'run.json'}", flush=True)
    return 0


def _benchmark(args: argparse.Namespace) -> int:
    from aether.evaluation.benchmark import benchmark

    benchmark(
        args.protocol,
        args.seeds,
        args.output_dir,
        workers=args.workers,
        synthetic_only=args.synthetic_only,
    )
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
    verified = verify_lineage(manifest, record)
    manifest["run_json_sha256"] = hashlib.sha256(record_bytes).hexdigest()
    manifest["run_id"] = record.run_id
    manifest["export_lineage_check"] = verified
    # The dataset manifest and normalized records travel with the archive; raw files stay
    # referenced by hash (they are tracked in the repository).
    evidence = {}
    if record.input_dataset is not None:
        dataset = manifest["input_dataset"]
        for rel in (dataset["manifest_path"], dataset["normalized_path"]):
            evidence[f"inputs/{rel}"] = (_repo_root() / rel).read_bytes()
    manifest["archive_members_sha256"] = {
        name: hashlib.sha256(data).hexdigest() for name, data in sorted(evidence.items())
    }
    performance_bytes = None
    performance_path = run_dir / "performance.json"
    if performance_path.is_file():
        from aether.contracts.models import RunPerformance

        performance = RunPerformance.model_validate_json(performance_path.read_bytes())
        if performance.run_id != record.run_id:
            raise ValueError("performance.json belongs to a different run")
        performance_bytes = performance_path.read_bytes()
        manifest["performance_json_sha256"] = hashlib.sha256(performance_bytes).hexdigest()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("run.json", record_bytes)
        archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        if performance_bytes is not None:
            archive.writestr("performance.json", performance_bytes)
        for name, data in sorted(evidence.items()):
            archive.writestr(name, data)
    return 0


def verify_export(archive_path: str | Path) -> dict:
    """Reload an export: record, manifest, member hashes and lineage. Raises on any mismatch."""
    from aether.contracts.models import RunPerformance, RunRecord

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        for required in ("run.json", "manifest.json"):
            if required not in names:
                raise LineageError(f"archive lacks {required}")
        record_bytes = archive.read("run.json")
        manifest = json.loads(archive.read("manifest.json"))
        record = RunRecord.model_validate_json(record_bytes)
        if hashlib.sha256(record_bytes).hexdigest() != manifest.get("run_json_sha256"):
            raise LineageError("run.json bytes differ from manifest run_json_sha256")
        if manifest.get("run_id") != record.run_id:
            raise LineageError("manifest run_id differs from run.json")
        if "performance.json" in names:
            performance_bytes = archive.read("performance.json")
            performance = RunPerformance.model_validate_json(performance_bytes)
            if performance.run_id != record.run_id:
                raise LineageError("performance.json belongs to a different run")
            if hashlib.sha256(performance_bytes).hexdigest() != manifest.get(
                "performance_json_sha256"
            ):
                raise LineageError("performance.json bytes differ from the manifest")
        members = manifest.get("archive_members_sha256", {})
        for name, digest in members.items():
            if name not in names or hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise LineageError(f"archive member {name} is missing or altered")
        if record.input_dataset is not None:
            dataset = manifest["input_dataset"]
            for rel, digest in (
                (dataset["manifest_path"], record.input_dataset.manifest_sha256),
                (dataset["normalized_path"], record.input_dataset.normalized_sha256),
            ):
                member = f"inputs/{rel}"
                if member not in members or members[member] != digest:
                    raise LineageError(f"archive lacks verified dataset evidence {member}")
    summary = verify_lineage(manifest, record)
    return {"run_id": record.run_id, **summary}


def _verify_export(args: argparse.Namespace) -> int:
    summary = verify_export(args.archive)
    json.dump(summary, sys.stdout, indent=2, sort_keys=True)
    print()
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
    p.add_argument("--synthetic-only", action="store_true", help="ignore the plume dataset")
    p.set_defaults(func=_windows)
    p = sub.add_parser("simulate", help="run one or more closed-loop policies")
    p.add_argument("--config", required=True)
    p.add_argument("--family")
    p.add_argument("--seed", type=int)
    p.add_argument("--policies", default="largest_first,adaptive_eig")
    p.add_argument("--output-dir", default="runs")
    p.add_argument("--synthetic-only", action="store_true", help="ignore the plume dataset")
    p.set_defaults(func=_simulate)
    p = sub.add_parser("benchmark", help="run the configured tuning-seed benchmark")
    p.add_argument("--protocol", required=True)
    p.add_argument("--seeds", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument(
        "--synthetic-only",
        action="store_true",
        help="ignore the plume dataset in every family (uniform fill; recorded in the results)",
    )
    p.set_defaults(func=_benchmark)
    p = sub.add_parser("export", help="validate and package a run artifact")
    p.add_argument("--run-dir", default="runs")
    p.add_argument("--run-id", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=_export)
    p = sub.add_parser("verify-export", help="reload an export and re-check its lineage")
    p.add_argument("--archive", required=True)
    p.set_defaults(func=_verify_export)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
