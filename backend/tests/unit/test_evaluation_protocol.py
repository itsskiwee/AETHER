"""EVL-05: holdout seeds are refused unless the protocol is locked, committed and tagged.

Uses a throwaway local git repository (no network).
"""

import json
import shutil
import subprocess

import pytest

from aether.evaluation.freeze import scientific_identity, write_freeze
from aether.evaluation.protocol import (
    ProtocolLockError,
    check_seed_access,
    load_protocol,
    read_seeds,
)


def test_repo_protocol_loads_and_seed_lists_are_disjoint(repo_root):
    proto = load_protocol(repo_root / "experiments/protocol.yaml")
    dev = read_seeds(repo_root / proto.tuning_seeds)
    hold = read_seeds(repo_root / proto.holdout_seeds)
    assert not set(dev) & set(hold)
    assert proto.primary_comparison[0].value == "adaptive_eig"


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path, repo_root):
    """A throwaway repository holding every scientific input the freeze identity covers."""
    exp = tmp_path / "experiments"
    exp.mkdir()
    for name in ("protocol.yaml", "seeds_dev.txt", "seeds_holdout.txt"):
        shutil.copy(repo_root / "experiments" / name, exp / name)
    shutil.copytree(repo_root / "configs", tmp_path / "configs")
    manifest = json.loads((repo_root / "data/manifests/emit_permian.json").read_text())
    for rel in ["data/manifests/emit_permian.json", manifest["normalized"]["path"],
                *(r["path"] for r in manifest["raw_files"])]:  # fmt: skip
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(repo_root / rel, tmp_path / rel)
    for name in ("ephemeris", "eop"):  # read-only pinned inputs, linked rather than copied
        (tmp_path / "data" / name).symlink_to(repo_root / "data" / name, target_is_directory=True)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "protocol")
    return tmp_path


def _lock(repo, commit=True, tag=True, freeze=True):
    path = repo / "experiments/protocol.yaml"
    path.write_text(path.read_text().replace("locked: false", "locked: true"))
    if freeze:
        write_freeze(repo)
        _git(repo, "add", "experiments/freeze.json")
    if commit:
        _git(repo, "commit", "-q", "-am", "lock protocol")
    if tag:
        _git(repo, "tag", "protocol-v1-locked")
    return path


def test_tuning_seeds_always_allowed(repo):
    path = repo / "experiments/protocol.yaml"
    assert check_seed_access(load_protocol(path), path, repo / "experiments/seeds_dev.txt") is None


def test_holdout_refused_while_unlocked(repo):
    path = repo / "experiments/protocol.yaml"
    with pytest.raises(ProtocolLockError, match="locked: false"):
        check_seed_access(load_protocol(path), path, repo / "experiments/seeds_holdout.txt")


def test_holdout_refused_when_lock_flag_not_committed(repo):
    path = _lock(repo, commit=False, tag=False)
    with pytest.raises(ProtocolLockError, match="uncommitted"):
        check_seed_access(load_protocol(path), path, repo / "experiments/seeds_holdout.txt")


def test_holdout_refused_without_tag(repo):
    path = _lock(repo, tag=False)
    with pytest.raises(ProtocolLockError, match="no git tag"):
        check_seed_access(load_protocol(path), path, repo / "experiments/seeds_holdout.txt")


def test_holdout_allowed_when_locked_committed_and_tagged(repo):
    path = _lock(repo)
    tag = check_seed_access(load_protocol(path), path, repo / "experiments/seeds_holdout.txt")
    assert tag == "protocol-v1-locked"


def test_editing_protocol_after_tag_reopens_the_lock(repo):
    path = _lock(repo)
    path.write_text(path.read_text() + "\n# edited after seeing results\n")
    _git(repo, "commit", "-q", "-am", "edit after lock")
    with pytest.raises(ProtocolLockError, match="no git tag"):
        check_seed_access(load_protocol(path), path, repo / "experiments/seeds_holdout.txt")


def test_unknown_seed_file_refused(repo):
    path = repo / "experiments/protocol.yaml"
    other = repo / "experiments/seeds_other.txt"
    other.write_text("2000\n2001\n")
    with pytest.raises(ProtocolLockError, match="neither"):
        check_seed_access(load_protocol(path), path, other)


def test_overlapping_seed_lists_refused(repo):
    path = repo / "experiments/protocol.yaml"
    (repo / "experiments/seeds_dev.txt").write_text("1000\n2000\n")
    with pytest.raises(ProtocolLockError, match="overlap"):
        check_seed_access(load_protocol(path), path, repo / "experiments/seeds_dev.txt")


def test_read_seeds_rejects_duplicates_and_garbage(tmp_path):
    f = tmp_path / "s.txt"
    f.write_text("1\n1\n")
    with pytest.raises(ValueError, match="duplicate"):
        read_seeds(f)
    f.write_text("1\nabc\n")
    with pytest.raises(ValueError, match="not an integer"):
        read_seeds(f)
    f.write_text("# header\n5  # comment\n\n6\n")
    assert read_seeds(f) == (5, 6)


def _holdout(repo):
    path = repo / "experiments/protocol.yaml"
    return check_seed_access(load_protocol(path), path, repo / "experiments/seeds_holdout.txt")


def test_freeze_identity_binds_configs_dataset_seeds_code_and_runtime(repo):
    identity = scientific_identity(repo)
    assert "configs/base.yaml" in identity["configs_sha256"]
    assert len(identity["family_config_hashes"]) == 6
    assert len(identity["dataset"]["files_sha256"]) == 42
    assert set(identity["seeds"]) == {"experiments/seeds_dev.txt", "experiments/seeds_holdout.txt"}
    assert len(identity["code"]["aether_package_sha256"]) == 64
    assert "data/ephemeris/de421.bsp" in identity["runtime_inputs"]["pinned_data_sha256"]
    assert "commit" not in json.dumps(identity)  # no self-referential git hashes


def test_holdout_refused_without_a_frozen_identity(repo):
    _lock(repo, freeze=False)
    with pytest.raises(ProtocolLockError, match="freeze.json is missing"):
        _holdout(repo)


def test_freeze_committed_after_the_tag_is_refused(repo):
    _lock(repo, freeze=False)
    write_freeze(repo)
    _git(repo, "add", "experiments/freeze.json")
    _git(repo, "commit", "-q", "-m", "freeze after lock")
    with pytest.raises(ProtocolLockError, match="does not contain"):
        _holdout(repo)


@pytest.mark.parametrize(
    "rel, edit",
    [
        ("configs/base.yaml", lambda t: t.replace("count: 20 ", "count: 21 ")),
        ("configs/scenarios/m2_pod_optimistic.yaml", lambda t: t + "\n# drift\n"),
        ("data/normalized/emit_permian_plumes.json", lambda t: t.replace("490.7823", "490.7824")),
        ("experiments/seeds_holdout.txt", lambda t: t + "999999\n"),
    ],
)
def test_committed_scientific_drift_after_the_tag_is_refused(repo, rel, edit):
    _lock(repo)
    assert _holdout(repo) == "protocol-v1-locked"
    path = repo / rel
    changed = edit(path.read_text())
    assert changed != path.read_text()
    path.write_text(changed)
    _git(repo, "commit", "-q", "-am", f"drift {rel}")
    with pytest.raises(ProtocolLockError, match="drifted"):
        _holdout(repo)


def test_uncommitted_scientific_input_is_refused(repo):
    _lock(repo)
    (repo / "configs/base.yaml").write_text((repo / "configs/base.yaml").read_text() + "\n")
    with pytest.raises(ProtocolLockError, match="uncommitted scientific inputs"):
        _holdout(repo)


def test_code_drift_is_refused(repo, monkeypatch):
    _lock(repo)
    import aether.evaluation.matrix as matrix

    monkeypatch.setattr(matrix, "code_sha256", lambda: "f" * 64)
    with pytest.raises(ProtocolLockError, match="code.aether_package_sha256"):
        _holdout(repo)
