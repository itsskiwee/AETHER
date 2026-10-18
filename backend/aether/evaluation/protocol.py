"""Pre-registered benchmark protocol: loading, seed lists and the holdout lock (EVL-05, PRD 9.4).

Holdout seeds may run only when ``experiments/protocol.yaml`` says ``locked: true`` AND that file
is committed with no local edits AND a git tag contains the last commit that touched it AND the
committed scientific identity ``experiments/freeze.json`` (``freeze.py``: configs, dataset, seeds,
code, ephemeris/EOP, packages) is in the same tag and still matches. The flag alone is not
enough: anyone can flip a flag after seeing results, but a tagged commit records when the
protocol was frozen, and the identity check rejects running it against drifted inputs.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from aether.contracts.enums import PolicyId


class ProtocolLockError(RuntimeError):
    """Raised when holdout seeds are requested without a verifiably locked protocol."""


class DiscriminabilityGateSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    require: str
    report: tuple[str, ...]
    on_fail: str


class AnalysisSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pairing: str
    statistic: str
    ci: str
    resamples: int = Field(ge=100)
    level: float = Field(gt=0, lt=1)


class Protocol(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_version: int
    locked: bool
    base_config: str
    families: tuple[str, ...]
    policies: tuple[PolicyId, ...]
    tuning_seeds: str
    holdout_seeds: str
    primary_metric: str
    primary_comparison: tuple[PolicyId, PolicyId]
    mandatory_secondary_comparison: tuple[PolicyId, PolicyId]
    reference_policies: tuple[PolicyId, ...]
    secondary_metrics: tuple[str, ...]
    breakdowns: tuple[str, ...]
    discriminability_gate: DiscriminabilityGateSpec
    analysis: AnalysisSpec
    multiplicity: str
    seed_count_rule: str
    success_criterion: str


def load_protocol(path: str | Path) -> Protocol:
    with Path(path).open() as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    proto = Protocol.model_validate(data)
    overlap = set(proto.policies) & set(proto.reference_policies)
    if overlap:
        raise ValueError(f"reference policies may not compete: {sorted(overlap)}")
    return proto


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_seeds(path: str | Path) -> tuple[int, ...]:
    """One integer per line; blank lines and ``#`` comments ignored; duplicates rejected."""
    seeds = []
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        text = line.split("#", 1)[0].strip()
        if not text:
            continue
        try:
            seeds.append(int(text))
        except ValueError as exc:
            raise ValueError(f"{path}:{n}: not an integer seed: {text!r}") from exc
    if len(set(seeds)) != len(seeds):
        raise ValueError(f"{path} contains duplicate seeds")
    if not seeds:
        raise ValueError(f"{path} contains no seeds")
    return tuple(seeds)


GitRunner = Callable[[list[str], Path], str]


def _git(args: list[str], cwd: Path) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def verify_git_lock(protocol_path: Path, git: GitRunner = _git) -> str:
    """Return the tag that freezes ``protocol_path``; raise ProtocolLockError otherwise."""
    cwd = protocol_path.parent
    name = protocol_path.name
    try:
        git(["ls-files", "--error-unmatch", name], cwd)
    except subprocess.CalledProcessError as exc:
        raise ProtocolLockError(f"{protocol_path} is not tracked by git") from exc
    if git(["status", "--porcelain", "--", name], cwd):
        raise ProtocolLockError(f"{protocol_path} has uncommitted changes")
    commit = git(["log", "-n", "1", "--format=%H", "--", name], cwd)
    if not commit:
        raise ProtocolLockError(f"{protocol_path} has no commit history")
    tags = git(["tag", "--contains", commit], cwd).split()
    if not tags:
        raise ProtocolLockError(f"no git tag contains {commit[:12]}, the last protocol commit")
    return sorted(tags)[0]


def _repo_root_for(protocol_path: Path) -> Path:
    """Protocol paths are repo-relative; the protocol lives in ``<repo>/experiments/``."""
    return protocol_path.resolve().parent.parent


def check_seed_access(
    protocol: Protocol, protocol_path: str | Path, seeds_path: str | Path, git: GitRunner = _git
) -> str | None:
    """Gate every benchmark run. Returns the lock tag for holdout runs, ``None`` for tuning runs.

    Also refuses any seed list that overlaps the other list, and seed files that are neither the
    tuning nor the holdout list, so "holdout" can't be smuggled in under another filename.
    """
    protocol_path, seeds_path = Path(protocol_path), Path(seeds_path)
    root = _repo_root_for(protocol_path)
    tuning = (root / protocol.tuning_seeds).resolve()
    holdout = (root / protocol.holdout_seeds).resolve()
    overlap = set(read_seeds(tuning)) & set(read_seeds(holdout))
    if overlap:
        raise ProtocolLockError(f"tuning and holdout seeds overlap: {sorted(overlap)[:5]}")
    target = seeds_path.resolve()
    if target == tuning:
        return None
    if target != holdout:
        raise ProtocolLockError(f"{seeds_path} is neither the tuning nor the holdout seed list")
    if not protocol.locked:
        raise ProtocolLockError("holdout seeds requested but protocol.yaml has locked: false")
    # The tag must also freeze every result-affecting input, not only this file (freeze.py).
    from aether.evaluation.freeze import verify_freeze

    return verify_freeze(root, git)
