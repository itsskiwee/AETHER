"""Parallel, resumable execution of a family x policy x seed run matrix (G4.5, SCI-10, EVL-04).

Each task is one (family, seed) pair and runs every requested policy in the same worker
process, so the runner's in-process window cache is reused across policies. A worker returns
a compact, deterministic per-run record:

- ``scores``: everything ``metrics.score_run`` reports;
- ``capacity``: ``reference.capacity_report`` (passes, acquisitions per pass, capacity/demand);
- ``calibration``: the (p_active, z_true, flux interval, true Q) points behind the scores, so
  reliability and coverage can be analysed later without keeping 2 MB RunRecords;
- ``input_dataset``: the run's pinned plume-dataset reference when the runner provides one.

Measured wall time is written to a separate, explicitly nondeterministic ``timing.jsonl``. Per-run
records live at ``<out_dir>/records/<family>/<policy>/<seed>.json`` and are reused on a rerun
only if their identity (config hashes, code SHA-256 of the imported package, policy, seed)
matches exactly.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

import aether
from aether import __version__
from aether.config import ScenarioBundle, load_scenario
from aether.contracts.enums import PolicyId
from aether.evaluation.metrics import _collect_points, evaluation_times, score_run
from aether.evaluation.reference import capacity_report

RunFn = Callable[[ScenarioBundle, PolicyId, int], tuple]


@dataclass(frozen=True)
class MatrixTask:
    family: str
    seed: int
    policies: tuple[str, ...]


def family_bundle(repo: Path, base_config: str, family: str, seed: int) -> ScenarioBundle:
    scenarios = repo / "configs" / "scenarios"
    return load_scenario(repo / base_config, scenarios / f"{family}.yaml", seed=seed)


def calibration_points(run, truth, cfg) -> list[list]:
    """[hours_from_t0, source_id, p_active, z_true, ci_lo_kg_h, ci_hi_kg_h, true_Q_kg_h]."""
    times = evaluation_times(truth.epoch_utc, truth.hours, cfg.evaluation.eval_interval_hours)
    return [
        [
            pt.hours_from_t0,
            pt.source_id,
            pt.p_active,
            pt.z_true,
            pt.flux_ci90_kg_h[0],
            pt.flux_ci90_kg_h[1],
            float(truth.sources[pt.source_id].median_flux_kg_h),
        ]
        for pt in _collect_points(run, truth, times)
    ]


_CODE_SHA256: str | None = None


def code_sha256() -> str:
    """SHA-256 over every ``*.py`` file of the imported ``aether`` package (relative path + bytes).

    This is the code that actually runs, so a runner/planner/belief edit changes the identity even
    when ``__version__`` does not. Raises if the package source cannot be read: a record whose code
    identity is unknown is never reused.
    """
    global _CODE_SHA256
    if _CODE_SHA256 is None:
        root = Path(aether.__file__).resolve().parent
        files = sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
        if not files:
            raise RuntimeError(f"cannot determine code identity: no sources under {root}")
        h = hashlib.sha256()
        for path in files:
            rel = path.relative_to(root).as_posix().encode()
            data = path.read_bytes()
            h.update(len(rel).to_bytes(8, "little") + rel + len(data).to_bytes(8, "little") + data)
        _CODE_SHA256 = h.hexdigest()
    return _CODE_SHA256


# Runtime inputs outside config_hash that change results (Claude-1 review, 18 Oct 2026).
RESULT_PACKAGES = ("numpy", "scipy", "ortools", "sgp4", "skyfield", "astropy", "pydantic", "pyyaml")
PINNED_DATA = ("data/ephemeris/manifest.json", "data/eop/manifest.json")
_RUNTIME_INPUTS: dict[str, dict] = {}


def runtime_inputs(repo: Path) -> dict:
    """SHA-256 of the pinned ephemeris/EOP manifests and every file they sit beside, plus versions
    of result-affecting packages. Raises if a pinned manifest is missing: no unknown identity."""
    key = str(repo)
    if key not in _RUNTIME_INPUTS:
        from aether.cli import _package_version

        data = {}
        for rel in PINNED_DATA:
            manifest = repo / rel
            if not manifest.is_file():
                raise RuntimeError(f"cannot determine runtime identity: {rel} missing")
            for path in sorted(p for p in manifest.parent.iterdir() if p.is_file()):
                data[path.relative_to(repo).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        versions = {name: _package_version(name) for name in RESULT_PACKAGES}
        if any(v is None for v in versions.values()):
            raise RuntimeError(f"cannot determine package versions: {versions}")
        _RUNTIME_INPUTS[key] = {"pinned_data_sha256": data, "package_versions": versions}
    return _RUNTIME_INPUTS[key]


def _identity(bundle: ScenarioBundle, family: str, policy: str, seed: int, repo: Path) -> dict:
    return {
        "family": family,
        "policy": policy,
        "seed": seed,
        "model_config_hash": bundle.model.config_hash(),
        "truth_config_hash": bundle.truth.config_hash(),
        "code_version": __version__,
        "code_sha256": code_sha256(),
        "runtime_inputs": runtime_inputs(repo),
    }


def _record_path(out_dir: Path, family: str, policy: str, seed: int) -> Path:
    return out_dir / "records" / family / policy / f"{seed}.json"


def _run_task(
    repo: str, base_config: str, task: MatrixTask, out_dir: str, run_fn: RunFn | None = None
) -> list[dict]:
    """Worker entry point (top level so it pickles by reference for the process pool)."""
    if run_fn is None:
        from aether.evaluation.benchmark import default_run_fn as run_fn

    repo_p, out_p = Path(repo), Path(out_dir)
    bundle = family_bundle(repo_p, base_config, task.family, task.seed)
    timings = []
    for policy in task.policies:
        identity = _identity(bundle, task.family, policy, task.seed, repo_p)
        path = _record_path(out_p, task.family, policy, task.seed)
        if path.exists() and json.loads(path.read_text())["identity"] == identity:
            continue
        started = perf_counter()
        run, truth = run_fn(bundle, PolicyId(policy), task.seed)
        elapsed = perf_counter() - started
        if run.policy_id.value != policy or run.seed != task.seed or run.family != task.family:
            raise RuntimeError(f"runner mislabelled run {run.run_id}")
        cfg = bundle.model
        dataset = getattr(run, "input_dataset", None)
        record = {
            "identity": identity,
            "run_id": run.run_id,
            "scores": score_run(run, truth, cfg),
            "capacity": asdict(capacity_report(run, cfg.horizon_hours)),
            "input_dataset": None if dataset is None else dataset.model_dump(mode="json"),
            "calibration": calibration_points(run, truth, cfg),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
        timings.append({"run_id": run.run_id, "family": task.family, "policy": policy,
                        "seed": task.seed, "complete_run_elapsed_s": elapsed})  # fmt: skip
    return timings


def execution_environment(repo: Path) -> dict:
    def git(*args: str) -> str | None:
        try:
            out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                                 check=True)  # fmt: skip
        except (OSError, subprocess.CalledProcessError):
            return None
        return out.stdout.strip()

    return {
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty_paths": (git("status", "--porcelain") or "").splitlines(),
        "code_version": __version__,
        "code_sha256": code_sha256(),
        "runtime_inputs": runtime_inputs(repo),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
    }


def run_matrix(
    repo: Path,
    base_config: str,
    families: Sequence[str],
    policies: Sequence[str],
    seeds: Sequence[int],
    out_dir: Path,
    workers: int = 1,
    log: Callable[[str], None] = print,
    run_fn: RunFn | None = None,
) -> dict[tuple[str, str, int], dict]:
    """Run (or reuse) every record; return them keyed by (family, policy, seed)."""
    repo, out_dir = repo.resolve(), out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = [MatrixTask(f, s, tuple(policies)) for f in families for s in seeds]
    started = perf_counter()
    timing_path = out_dir / "timing.jsonl"
    with timing_path.open("a", encoding="utf-8") as timing_fh:
        if workers <= 1:
            done = (_run_task(str(repo), base_config, t, str(out_dir), run_fn) for t in tasks)
            for i, timings in enumerate(done, 1):
                _log_timings(timing_fh, timings, i, len(tasks), started, log)
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_run_task, str(repo), base_config, t, str(out_dir), run_fn)
                           for t in tasks]  # fmt: skip
                for i, fut in enumerate(as_completed(futures), 1):
                    _log_timings(timing_fh, fut.result(), i, len(tasks), started, log)
    records = {}
    for f in families:
        for p in policies:
            for s in seeds:
                records[(f, p, s)] = json.loads(_record_path(out_dir, f, p, s).read_text())
    return records


def _log_timings(fh, timings: list[dict], i: int, n: int, started: float, log) -> None:
    for t in timings:
        fh.write(json.dumps(t, sort_keys=True) + "\n")
    fh.flush()
    log(f"[{i}/{n}] {perf_counter() - started:.0f} s elapsed; "
        + ", ".join(f"{t['family']}/{t['policy']}/{t['seed']} {t['complete_run_elapsed_s']:.1f}s"
                    for t in timings))  # fmt: skip
