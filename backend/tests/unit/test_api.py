"""UI-01..05 API: read-only artifact routes, missing/invalid artifact states, benchmark reload."""

import hashlib
import json
import shutil

import pytest
import yaml

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from aether.api import create_app  # noqa: E402
from aether.contracts import PolicyId, RunRecord, Source  # noqa: E402


def _run(run_id="run-a"):
    return RunRecord(
        run_id=run_id, policy_id=PolicyId.ADAPTIVE_EIG, scenario_id="s", family="m0_well_specified",
        seed=1000, model_config_hash="m", truth_config_hash="t", code_version="test",
        sources=(Source(id="S0", lon=-103.0, lat=32.0),), windows=(), plans=(), validations=(),
        utilities=(), acquisitions=(), beliefs=(), events=(),
    )  # fmt: skip


@pytest.fixture
def project(tmp_path, repo_root):
    """A throwaway project tree: real configs and protocol, empty runs/ and benchmark dirs."""
    shutil.copytree(repo_root / "configs", tmp_path / "configs")
    shutil.copytree(repo_root / "experiments", tmp_path / "experiments")
    (tmp_path / "runs" / "run-a").mkdir(parents=True)
    (tmp_path / "runs" / "run-a" / "run.json").write_text(_run().model_dump_json())
    return tmp_path


@pytest.fixture
def client(project):
    return TestClient(create_app(project_root=project))


def test_every_route_is_read_only(client):
    methods = {m for r in client.app.routes for m in getattr(r, "methods", ())}
    assert methods <= {"GET", "HEAD"}


def test_runs_listed_and_reloaded_through_the_contract(client):
    assert [r["run_id"] for r in client.get("/api/runs").json()] == ["run-a"]
    body = client.get("/api/runs/run-a").json()
    assert RunRecord.model_validate(body) == _run()


def test_invalid_run_is_reported_not_hidden(client, project):
    (project / "runs" / "bad").mkdir()
    (project / "runs" / "bad" / "run.json").write_text('{"run_id": "bad"}')
    assert client.get("/api/runs/bad").status_code == 422
    assert client.get("/api/runs/missing").status_code == 404


@pytest.mark.parametrize("run_id", ["..", "..%2F..%2Fconfigs", "%2E%2E"])
def test_path_traversal_rejected(client, run_id):
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_example_run_listed_when_runs_dir_absent(tmp_path):
    (tmp_path / "docs" / "examples").mkdir(parents=True)
    (tmp_path / "docs" / "examples" / "run.json").write_text(_run("example").model_dump_json())
    c = TestClient(create_app(project_root=tmp_path))
    assert [r["run_id"] for r in c.get("/api/runs").json()] == ["example"]
    assert c.get("/api/example").json()["run_id"] == "example"
    assert c.get("/api/runs/example").status_code == 200


def test_real_archive_does_not_mix_example_fixture_into_run_list(client, project):
    example_dir = project / "docs" / "examples"
    example_dir.mkdir(parents=True)
    (example_dir / "run.json").write_text(_run("example").model_dump_json())
    assert [row["run_id"] for row in client.get("/api/runs").json()] == ["run-a"]
    assert client.get("/api/example").json()["run_id"] == "example"


def test_checked_in_example_run_loads_through_api(repo_root, tmp_path):
    """The API serves the L1 example artifact unchanged through the current contract."""
    client = TestClient(create_app(run_root=tmp_path / "empty-runs", project_root=repo_root))
    expected = RunRecord.model_validate_json(
        (repo_root / "docs/examples/run.json").read_text(encoding="utf-8")
    )
    response = client.get("/api/example")
    assert response.status_code == 200
    actual = RunRecord.model_validate(response.json())
    assert actual == expected
    assert actual.plans
    by_window = {window.id: window for window in actual.windows}
    for plan in actual.plans:
        assert plan.selections is not None
        assert all(
            selection.option_id
            in {option.option_id for option in by_window[selection.window_id].options}
            for selection in plan.selections
        )


def test_missing_benchmark_artifacts_are_404(client):
    assert client.get("/api/benchmark-results.csv").status_code == 404
    assert client.get("/api/benchmark-confidence-intervals.json").status_code == 404


def test_malformed_ci_report_is_422(client, project):
    (project / "runs" / "benchmark").mkdir()
    (project / "runs" / "benchmark" / "benchmark-confidence-intervals.json").write_text("{")
    assert client.get("/api/benchmark-confidence-intervals.json").status_code == 422
    (project / "runs" / "benchmark" / "benchmark-confidence-intervals.json").write_text("[]")
    assert client.get("/api/benchmark-confidence-intervals.json").status_code == 422


def test_evaluator_output_reloads_unchanged(client, project, repo_root):
    """The files ``evaluation.benchmark`` writes are what the API serves (fake runner)."""
    from aether.evaluation.benchmark import benchmark
    from tests.unit.test_evaluation_benchmark import fake_run

    out = project / "runs" / "benchmark"
    written = benchmark(project / "experiments/protocol.yaml",
                        project / "experiments/seeds_dev.txt", out, run_fn=fake_run)  # fmt: skip
    assert client.get("/api/benchmark-confidence-intervals.json").json() == written
    rows = client.get("/api/benchmark-results.csv").json()
    assert rows and {"n_seeds", "n_defined", "n_undefined", "mean", "sd"} <= set(rows[0])


def test_protocol_view_reports_lock_state(client):
    proto = client.get("/api/benchmark-protocol").json()
    assert proto["locked"] is False
    assert proto["primary_comparison"] == ["adaptive_eig", "largest_first"]
    assert len(proto["families"]) == 6
    assert "adaptive_eig" in proto["policies"]


def _write_project_dataset(project):
    data_dir = project / "data" / "normalized"
    data_dir.mkdir(parents=True)
    source_hash = "a" * 64
    record = {
        "id": "nasa:fixture-plume-1",
        "provenance_class": "REAL_OBSERVATION",
        "provider": "NASA LP DAAC",
        "native_id": "fixture-plume-1",
        "dataset_version": "002",
        "acquisition_time_utc": "2023-08-14T18:02:00Z",
        "lon": -103.2,
        "lat": 32.1,
        "geometry_geojson": None,
        "acquisition_id": None,
        "emission_rate_kg_h": None,
        "emission_rate_uncertainty_kg_h": None,
        "uncertainty_kind": "UNKNOWN",
        "missing_rate_reason": "CRITERIA_NOT_MET",
        "quality_flags": [],
        "raw_properties": {"Emissions Rate Estimate (kg/hr)": "N/A"},
        "source": {
            "provider": "NASA LP DAAC",
            "dataset": "EMITL2BCH4PLM",
            "version": "002",
            "url": "https://example.invalid/emit-metadata.json",
            "license_url": "https://example.invalid/license",
            "citation_text": "API fixture only",
            "retrieved_at_utc": "2026-10-18T12:00:00Z",
            "sha256": source_hash,
        },
    }
    normalized_path = "data/normalized/emit_permian_plumes.json"
    normalized_bytes = (json.dumps([record], sort_keys=True, separators=(",", ":")) + "\n").encode()
    (project / normalized_path).write_bytes(normalized_bytes)
    manifest = {
        "dataset_id": "emit-l2b-ch4plm-002-permian-test",
        "provider": "NASA LP DAAC",
        "dataset": "EMITL2BCH4PLM",
        "version": "002",
        "retrieval": {"status": "PARTIAL", "retrieved_at_utc": None, "evidence": "API fixture"},
        "raw_files": [],
        "normalized": {
            "path": normalized_path,
            "sha256": hashlib.sha256(normalized_bytes).hexdigest(),
            "record_count": 1,
        },
    }
    manifest_path = project / "data" / "manifests" / "emit_permian.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    manifest_path.write_bytes(manifest_bytes)
    config_path = project / "configs" / "base.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["sources"]["plume_dataset"] = {
        "manifest": "data/manifests/emit_permian.json",
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return normalized_path


def test_project_historical_context_reports_explicit_synthetic_only(client):
    response = client.get("/api/project/historical-context")
    assert response.status_code == 200
    assert response.json() == {
        "status": "synthetic_only",
        "input_dataset": None,
        "manifest": None,
        "observations": [],
    }


def test_project_historical_context_reads_pinned_real_records(client, project):
    _write_project_dataset(project)
    response = client.get("/api/project/historical-context")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pinned"
    assert body["input_dataset"]["dataset_id"] == "emit-l2b-ch4plm-002-permian-test"
    assert body["observations"][0]["provenance_class"] == "REAL_OBSERVATION"
    assert body["observations"][0]["acquisition_time_utc"] == "2023-08-14T18:02:00Z"
    assert body["observations"][0]["emission_rate_kg_h"] is None
    assert body["observations"][0]["missing_rate_reason"] == "CRITERIA_NOT_MET"
    assert body["observations"][0]["uncertainty_kind"] == "UNKNOWN"
    assert body["observations"][0]["source"]["sha256"] == "a" * 64


def test_project_historical_context_fails_on_hash_mismatch(client, project):
    normalized_path = _write_project_dataset(project)
    (project / normalized_path).write_text("[]\n", encoding="utf-8")
    response = client.get("/api/project/historical-context")
    assert response.status_code == 422
    assert "SHA-256 mismatch" in response.json()["detail"]


def test_run_historical_context_does_not_substitute_current_dataset(client):
    response = client.get("/api/runs/run-a/historical-context")
    assert response.status_code == 404
    assert "no pinned dataset reference" in response.json()["detail"]


def test_explicit_null_run_dataset_ref_reports_synthetic_only(client, monkeypatch):
    original_dump = RunRecord.model_dump

    def with_explicit_null(self, *args, **kwargs):
        return {**original_dump(self, *args, **kwargs), "input_dataset": None}

    monkeypatch.setattr(RunRecord, "model_dump", with_explicit_null)
    response = client.get("/api/runs/run-a/historical-context")
    assert response.status_code == 200
    assert response.json() == {
        "status": "synthetic_only",
        "input_dataset": None,
        "manifest": None,
        "observations": [],
    }


def test_timing_sidecar_is_served_separately_and_zero_is_invalid(client, project):
    path = project / "runs" / "benchmark" / "development-timing.json"
    path.parent.mkdir()
    report = {
        "note": "Measured wall time; nondeterministic sidecar, not solver runtime.",
        "complete_comparison_elapsed_s": 12.25,
        "runs": [{"run_id": "run-a", "complete_run_elapsed_s": 3.5}],
    }
    path.write_text(json.dumps(report), encoding="utf-8")
    assert client.get("/api/development-timing.json").json() == report
    path.write_text(json.dumps(report | {"complete_comparison_elapsed_s": 0}), encoding="utf-8")
    assert client.get("/api/development-timing.json").status_code == 422


def test_project_snapshot_reads_model_side_config(client):
    snap = client.get("/api/project").json()
    assert snap["scenario"]["id"] and snap["benchmark_protocol"]["locked"] is False
    assert "truth" not in json.dumps(snap).lower().replace("truth_config_hash", "")


def test_run_manifest_is_archived_not_current_config(client, project):
    path = project / "runs/run-a/manifest.json"
    assert client.get("/api/runs/run-a/manifest.json").status_code == 404
    expected = {"input_sha256": {"data/old.json": "a" * 64}, "package_versions": {}}
    path.write_text(json.dumps(expected))
    assert client.get("/api/runs/run-a/manifest.json").json() == expected
    path.write_text("[]")
    assert client.get("/api/runs/run-a/manifest.json").status_code == 422
    assert client.get("/api/runs/missing/manifest.json").status_code == 404


def test_measured_timing_reloads_without_changing_run(client, project):
    path = project / "runs/benchmark/development-timing.json"
    path.parent.mkdir()
    expected = {
        "complete_comparison_elapsed_s": 42.75,
        "note": "Measured complete run, not solver runtime.",
        "runs": [{"run_id": "run-a", "complete_run_elapsed_s": 42.5}],
    }
    path.write_text(json.dumps(expected))
    before = client.get("/api/runs/run-a").content
    assert client.get("/api/development-timing.json").json() == expected
    assert client.get("/api/runs/run-a").content == before


@pytest.mark.parametrize("duration", [-1, None, True, "0", float("nan"), float("inf")])
def test_invalid_timing_is_rejected(client, project, duration):
    path = project / "runs/benchmark/development-timing.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "complete_comparison_elapsed_s": 5,
                "runs": [{"run_id": "run-a", "complete_run_elapsed_s": duration}],
            }
        )
    )
    assert client.get("/api/development-timing.json").status_code == 422


def test_unpinned_run_does_not_show_current_project_dataset(client, project):
    path = project / "data/manifests/emit_permian.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"dataset_id": "new-current-dataset"}')
    assert client.get("/api/runs/run-a/historical-context").status_code == 404
    assert client.get("/api/development-timing.json").status_code == 404


@pytest.fixture
def pinned_context(project, monkeypatch):
    """Exercise the agreed additive DATA-02 projection before its owner merges the contract."""
    import hashlib

    original_dump = RunRecord.model_dump
    records = [
        {
            "id": "NASA:test",
            "native_id": "test",
            "provider": "NASA LP DAAC",
            "dataset_version": "002",
            "provenance_class": "REAL_OBSERVATION",
            "acquisition_time_utc": "2023-01-01T00:00:00Z",
            "lon": -103,
            "lat": 32,
            "geometry_geojson": {"type": "Point", "coordinates": [-103, 32]},
            "acquisition_id": None,
            "emission_rate_kg_h": None,
            "emission_rate_uncertainty_kg_h": 20,
            "uncertainty_kind": "UNKNOWN",
            "missing_rate_reason": "CRITERIA_NOT_MET",
            "quality_flags": [],
            "raw_properties": {},
            "source": {
                "provider": "NASA LP DAAC",
                "dataset": "EMITL2BCH4PLM",
                "version": "002",
                "url": "https://example.org/provider-record",
                "license_url": None,
                "citation_text": "TEST ONLY",
                "retrieved_at_utc": "2026-01-01T00:00:00Z",
                "sha256": "a" * 64,
            },
        }
    ]
    normalized_path = project / "data/normalized/test.json"
    normalized_path.parent.mkdir(parents=True)
    normalized_path.write_text(json.dumps(records))
    norm_hash = hashlib.sha256(normalized_path.read_bytes()).hexdigest()
    manifest = {
        "dataset_id": "pinned-test",
        "normalized": {"path": "data/normalized/test.json", "sha256": norm_hash, "record_count": 1},
    }
    manifest_path = project / "data/manifests/emit_permian.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(manifest))
    ref = {
        "dataset_id": "pinned-test",
        "manifest_path": "data/manifests/emit_permian.json",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "normalized_sha256": norm_hash,
        "record_count": 1,
    }

    def with_dataset(self, *args, **kwargs):
        return {**original_dump(self, *args, **kwargs), "input_dataset": ref}

    monkeypatch.setattr(RunRecord, "model_dump", with_dataset)
    return ref, manifest_path, normalized_path, records


def test_pinned_context_preserves_null_and_unknown_uncertainty(client, pinned_context):
    ref, _, _, records = pinned_context
    response = client.get("/api/runs/run-a/historical-context")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["input_dataset"] == ref
    record = body["observations"][0]
    assert record["emission_rate_kg_h"] is None
    assert record["emission_rate_uncertainty_kg_h"] == 20
    assert record["uncertainty_kind"] == "UNKNOWN"
    assert record["provenance_class"] == "REAL_OBSERVATION"
    assert record["acquisition_time_utc"] == records[0]["acquisition_time_utc"]


@pytest.mark.parametrize("target", ["manifest", "normalized", "outside", "identity", "count"])
def test_pinned_context_rejects_changed_or_escaping_inputs(
    client, pinned_context, target, tmp_path
):
    ref, manifest_path, normalized_path, _ = pinned_context
    if target == "manifest":
        manifest_path.write_text("{}")
    elif target == "normalized":
        normalized_path.write_text("[]")
    elif target == "outside":
        outside = tmp_path.parent / "outside-manifest.json"
        outside.write_bytes(manifest_path.read_bytes())
        ref["manifest_path"] = str(outside)
    elif target == "identity":
        ref["normalized_sha256"] = "b" * 64
    else:
        ref["record_count"] = 2
    assert client.get("/api/runs/run-a/historical-context").status_code == 422
