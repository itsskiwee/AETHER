"""UI-01..05 API: read-only artifact routes, missing/invalid artifact states, benchmark reload."""

import json
import shutil

import pytest

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


def test_project_snapshot_reads_model_side_config(client):
    snap = client.get("/api/project").json()
    assert snap["scenario"]["id"] and snap["benchmark_protocol"]["locked"] is False
    assert "truth" not in json.dumps(snap).lower().replace("truth_config_hash", "")
