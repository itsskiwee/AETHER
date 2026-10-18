"""Scientific freeze identity: what a locked holdout run is allowed to depend on (EVL-05).

``experiments/freeze.json`` is a committed manifest of every result-affecting input:

- the protocol file and both seed lists (bytes);
- every file under ``configs/`` (bytes) and the resolved model/truth config hash of each
  protocol family on ``base_config``;
- the pinned plume dataset the base config names: its manifest, normalized records and every
  selected raw file (bytes, as listed by the manifest);
- the code identity of the imported ``aether`` package (``matrix.code_sha256``: relative path and
  bytes of every ``*.py`` file), the pinned ephemeris/EOP bytes and result-affecting package
  versions (``matrix.runtime_inputs``).

It holds no commit hashes, so it never refers to itself. The relationship to git is: the freeze
file and the locked protocol must both be tracked, unmodified, and contained in the lock tag that
``protocol.verify_git_lock`` returns; and the identity recomputed from the working tree and the
running code must equal the committed file exactly. Holdout entry also refuses uncommitted
changes under the scientific input paths. Any drift (config, code, data, seeds, packages,
ephemeris) is a ``ProtocolLockError``.

    python -m aether.evaluation.freeze write    # prepare the file for review, then commit + tag
    python -m aether.evaluation.freeze verify   # what holdout entry checks
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from aether.evaluation.protocol import (
    GitRunner,
    ProtocolLockError,
    _git,
    load_protocol,
    verify_git_lock,
)

FREEZE_VERSION = 1
FREEZE_PATH = "experiments/freeze.json"
# Uncommitted edits under these paths block holdout entry (the identity covers their bytes).
SCIENTIFIC_PATHS = ("configs", "experiments", "data/manifests", "data/normalized",
                    "data/raw/pinned_emit_permian_v1", "data/ephemeris", "data/eop",
                    "backend/aether")  # fmt: skip


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files(root: Path, rels) -> dict[str, str]:
    out = {}
    for rel in sorted(set(rels)):
        path = root / rel
        if not path.is_file():
            raise ProtocolLockError(f"scientific input {rel} is missing")
        out[rel] = _sha(path)
    return out


def scientific_identity(repo: Path, protocol_rel: str = "experiments/protocol.yaml") -> dict:
    """Recompute the freeze identity from the working tree and the running code."""
    from aether.config import load_scenario
    from aether.evaluation.matrix import code_sha256, runtime_inputs

    repo = repo.resolve()
    proto = load_protocol(repo / protocol_rel)
    configs = sorted(
        p.relative_to(repo).as_posix() for p in (repo / "configs").rglob("*") if p.is_file()
    )
    families = {}
    dataset_spec = None
    for family in proto.families:
        bundle = load_scenario(
            repo / proto.base_config, repo / "configs" / "scenarios" / f"{family}.yaml"
        )
        model, truth = bundle.model.config_hash(), bundle.truth.config_hash()
        families[family] = {"model": model, "truth": truth}
        dataset_spec = bundle.model.sources.plume_dataset
    dataset = None
    if dataset_spec is not None:
        manifest_rel = dataset_spec.manifest
        manifest = json.loads((repo / manifest_rel).read_bytes())
        rels = [manifest_rel, manifest["normalized"]["path"]]
        rels += [record["path"] for record in manifest["raw_files"]]
        dataset = {
            "dataset_id": manifest["dataset_id"],
            "manifest": manifest_rel,
            "manifest_sha256_configured": dataset_spec.manifest_sha256,
            "adapter_version": manifest.get("adapter_version"),
            "transformation_version": manifest.get("transformation_version"),
            "files_sha256": _files(repo, rels),
        }
    return {
        "freeze_version": FREEZE_VERSION,
        "protocol": _files(repo, [protocol_rel]),
        "seeds": _files(repo, [proto.tuning_seeds, proto.holdout_seeds]),
        "configs_sha256": _files(repo, configs),
        "family_config_hashes": families,
        "dataset": dataset,
        "code": {"aether_package_sha256": code_sha256()},
        "runtime_inputs": runtime_inputs(repo),
    }


def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def write_freeze(repo: Path) -> Path:
    path = repo.resolve() / FREEZE_PATH
    path.write_text(_canonical(scientific_identity(repo)), encoding="utf-8")
    return path


def _drift(frozen, current, prefix: str = "") -> list[str]:
    if isinstance(frozen, dict) and isinstance(current, dict):
        out = []
        for key in sorted(set(frozen) | set(current)):
            out += _drift(frozen.get(key), current.get(key), f"{prefix}{key}.")
        return out
    return [] if frozen == current else [prefix.rstrip(".")]


def verify_freeze(repo: Path, git: GitRunner = _git) -> str:
    """Holdout entry: tagged, clean and unchanged scientific identity. Returns the lock tag."""
    repo = repo.resolve()
    protocol_path = repo / "experiments/protocol.yaml"
    tag = verify_git_lock(protocol_path, git)
    freeze_path = repo / FREEZE_PATH
    if not freeze_path.is_file():
        raise ProtocolLockError(f"{FREEZE_PATH} is missing; the scientific identity is not frozen")
    try:
        git(["ls-files", "--error-unmatch", FREEZE_PATH], repo)
    except subprocess.CalledProcessError as exc:
        raise ProtocolLockError(f"{FREEZE_PATH} is not tracked by git") from exc
    commit = git(["log", "-n", "1", "--format=%H", "--", FREEZE_PATH], repo)
    if not commit or tag not in git(["tag", "--contains", commit], repo).split():
        raise ProtocolLockError(f"lock tag {tag} does not contain the last {FREEZE_PATH} commit")
    dirty = git(["status", "--porcelain", "--", *SCIENTIFIC_PATHS], repo)
    if dirty:
        raise ProtocolLockError(f"uncommitted scientific inputs: {dirty.splitlines()[:5]}")
    frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
    drift = _drift(frozen, scientific_identity(repo))
    if drift:
        raise ProtocolLockError(f"scientific identity drifted from {FREEZE_PATH}: {drift[:8]}")
    return tag


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("write", "verify", "show"))
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    args = ap.parse_args(argv)
    if args.action == "write":
        print(write_freeze(args.repo))
    elif args.action == "verify":
        print(verify_freeze(args.repo))
    else:
        sys.stdout.write(_canonical(scientific_identity(args.repo)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
