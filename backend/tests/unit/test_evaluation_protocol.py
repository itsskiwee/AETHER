"""EVL-05: holdout seeds are refused unless the protocol is locked, committed and tagged.

Uses a throwaway local git repository (no network).
"""

import shutil
import subprocess

import pytest

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
    exp = tmp_path / "experiments"
    exp.mkdir()
    for name in ("protocol.yaml", "seeds_dev.txt", "seeds_holdout.txt"):
        shutil.copy(repo_root / "experiments" / name, exp / name)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "protocol")
    return tmp_path


def _lock(repo, commit=True, tag=True):
    path = repo / "experiments/protocol.yaml"
    path.write_text(path.read_text().replace("locked: false", "locked: true"))
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
