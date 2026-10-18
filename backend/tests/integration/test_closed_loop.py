"""INT-04 determinism and PERF-01 timing separation on a short closed-loop run."""

from __future__ import annotations

import json
import zipfile

import pytest

from aether.cli import main
from aether.config import ScenarioBundle, ScenarioConfig, load_scenario
from aether.contracts.models import RunPerformance, RunRecord
from aether.simulation import runner

pytestmark = pytest.mark.slow


def _short(cfg: ScenarioConfig) -> ScenarioConfig:
    data = cfg.model_dump(mode="python")
    data["horizon_hours"] = 12
    data["sources"]["count"] = 6
    return ScenarioConfig.model_validate(data)


@pytest.fixture(scope="module")
def bundle(base_config_path):
    loaded = load_scenario(base_config_path, synthetic_only=True)
    return ScenarioBundle(model=_short(loaded.model), truth=_short(loaded.truth))


def _bytes(run: RunRecord) -> bytes:
    return run.model_dump_json().encode()


def test_same_seed_gives_identical_record_bytes_and_timing_stays_outside(bundle, monkeypatch):
    monkeypatch.setattr(runner, "_WINDOW_CACHE", {})
    first, performance = runner.run_policy_with_performance(bundle, "adaptive_eig", 1000)
    monkeypatch.setattr(runner, "_WINDOW_CACHE", {})  # recompute geometry too
    second = runner.run_policy(bundle, "adaptive_eig", 1000)
    assert _bytes(first) == _bytes(second)
    assert all(plan.runtime_s is None for plan in first.plans)
    assert first.input_dataset is None  # synthetic-only

    assert performance.run_id == first.run_id
    assert performance.measured is True
    assert not performance.windows_from_process_cache
    assert performance.windows_wall_s > 0
    assert performance.total_run_wall_s >= performance.windows_wall_s
    assert len(performance.plan_timings) >= len(first.plans)
    assert {t.revision for t in performance.plan_timings} == {p.revision for p in first.plans}
    assert all(t.policy_plan_wall_s > 0 for t in performance.plan_timings)
    assert "plan_timings" not in first.model_dump_json()


def test_policies_share_sources_and_windows(bundle):
    a = runner.run_policy(bundle, "largest_first", 1000)
    b, performance = runner.run_policy_with_performance(bundle, "adaptive_eig", 1000)
    assert a.sources == b.sources
    assert a.windows == b.windows
    assert performance.windows_from_process_cache


def test_export_carries_performance_separately(bundle, tmp_path):
    run, performance = runner.run_policy_with_performance(bundle, "largest_first", 1000)
    run_dir = tmp_path / run.run_id
    run_dir.mkdir()
    (run_dir / "run.json").write_text(run.model_dump_json())
    (run_dir / "manifest.json").write_text("{}")
    (run_dir / "performance.json").write_text(performance.model_dump_json())
    output = tmp_path / "export.zip"
    args = ["export", "--run-dir", str(tmp_path), "--run-id", run.run_id, "--output", str(output)]
    assert main(args) == 0
    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert RunPerformance.model_validate_json(archive.read("performance.json")) == performance
    assert len(manifest["performance_json_sha256"]) == 64

    (run_dir / "performance.json").write_text(
        performance.model_copy(update={"run_id": "other"}).model_dump_json()
    )
    with pytest.raises(ValueError, match="different run"):
        main(args)
