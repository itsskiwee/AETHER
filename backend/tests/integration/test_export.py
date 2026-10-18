"""Export reload and integrity must cover the exact archive member bytes."""

import hashlib
import json
import zipfile

from aether.cli import main
from aether.contracts import RunRecord


def test_export_digest_matches_nested_record_bytes(repo_root, tmp_path):
    example = RunRecord.model_validate_json((repo_root / "docs/examples/run.json").read_bytes())
    run_dir = tmp_path / example.run_id
    run_dir.mkdir()
    (run_dir / "run.json").write_text(example.model_dump_json())
    (run_dir / "manifest.json").write_text("{}")
    output = tmp_path / "export.zip"
    assert (
        main(
            [
                "export",
                "--run-dir",
                str(tmp_path),
                "--run-id",
                example.run_id,
                "--output",
                str(output),
            ]
        )
        == 0
    )
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
