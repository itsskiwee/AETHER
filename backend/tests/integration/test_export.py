"""Export reload and integrity must cover the exact archive member bytes and input lineage."""

import hashlib
import json
import zipfile

import pytest

from aether import cli
from aether.cli import LineageError, main, verify_export, verify_lineage
from aether.contracts import RunRecord


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _synthetic_manifest(repo_root, record):
    return {
        "lineage_version": cli.LINEAGE_VERSION,
        "synthetic_only": True,
        "plume_dataset": None,
        "input_dataset": None,
        "model_config_hash": record.model_config_hash,
        "truth_config_hash": record.truth_config_hash,
        "input_sha256": {rel: _sha(repo_root / rel) for rel in cli.PINNED_INPUTS},
    }


@pytest.fixture
def example(repo_root):
    return RunRecord.model_validate_json((repo_root / "docs/examples/run.json").read_bytes())


def _write_run(tmp_path, record, manifest):
    run_dir = tmp_path / record.run_id
    run_dir.mkdir()
    (run_dir / "run.json").write_text(record.model_dump_json())
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    return ["export", "--run-dir", str(tmp_path), "--run-id", record.run_id]


def test_export_digest_matches_nested_record_bytes(repo_root, tmp_path, example):
    args = _write_run(tmp_path, example, _synthetic_manifest(repo_root, example))
    output = tmp_path / "export.zip"
    assert main([*args, "--output", str(output)]) == 0
    with zipfile.ZipFile(output) as archive:
        encoded = archive.read("run.json")
        manifest = json.loads(archive.read("manifest.json"))
    reloaded = RunRecord.model_validate_json(encoded)
    assert reloaded == example
    assert reloaded.plans
    assert [p.selected_window_ids for p in reloaded.plans] == [
        p.selected_window_ids for p in example.plans
    ]
    assert manifest["run_json_sha256"] == hashlib.sha256(encoded).hexdigest()
    assert manifest["export_lineage_check"]["verified_input_files"] == len(cli.PINNED_INPUTS)
    assert verify_export(output)["run_id"] == example.run_id


def test_export_refuses_a_manifest_without_lineage(tmp_path, example):
    args = _write_run(tmp_path, example, {})
    with pytest.raises(LineageError, match="lineage_version"):
        main([*args, "--output", str(tmp_path / "x.zip")])
    assert not (tmp_path / "x.zip").exists()


def test_lineage_requires_every_pinned_input(repo_root, example):
    manifest = _synthetic_manifest(repo_root, example)
    del manifest["input_sha256"]["data/eop/finals2000A.all"]
    with pytest.raises(LineageError, match="lacks required evidence"):
        verify_lineage(manifest, example)


@pytest.mark.parametrize("key", ["/etc/passwd", "../outside.json", "data\\eop\\manifest.json"])
def test_lineage_paths_must_be_portable(repo_root, example, key):
    manifest = _synthetic_manifest(repo_root, example)
    manifest["input_sha256"][key] = "0" * 64
    with pytest.raises(LineageError, match="repo-relative"):
        verify_lineage(manifest, example)


def test_lineage_rejects_an_altered_input(repo_root, example, tmp_path):
    for rel in cli.PINNED_INPUTS:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((repo_root / rel).read_bytes())
    manifest = _synthetic_manifest(repo_root, example)
    assert verify_lineage(manifest, example, root=tmp_path)["input_dataset"] is None
    (tmp_path / "data/eop/manifest.json").write_text("{}")
    with pytest.raises(LineageError, match="altered"):
        verify_lineage(manifest, example, root=tmp_path)


def test_lineage_rejects_a_dataset_the_record_does_not_have(repo_root, example):
    manifest = _synthetic_manifest(repo_root, example)
    manifest["plume_dataset"] = {"manifest": "data/manifests/emit_permian.json"}
    with pytest.raises(LineageError, match="run record has none"):
        verify_lineage(manifest, example)


def test_lineage_rejects_a_config_hash_mismatch(repo_root, example):
    manifest = _synthetic_manifest(repo_root, example)
    manifest["model_config_hash"] = "f" * 64
    with pytest.raises(LineageError, match="model_config_hash"):
        verify_lineage(manifest, example)


def test_verify_export_detects_a_rewritten_member(repo_root, tmp_path, example):
    args = _write_run(tmp_path, example, _synthetic_manifest(repo_root, example))
    output = tmp_path / "export.zip"
    main([*args, "--output", str(output)])
    with zipfile.ZipFile(output) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    record = json.loads(members["run.json"])
    record["seed"] += 1
    members["run.json"] = json.dumps(record).encode()
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(tampered, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    with pytest.raises(LineageError, match="run_json_sha256"):
        verify_export(tampered)
