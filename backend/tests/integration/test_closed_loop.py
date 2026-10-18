"""INT-04 determinism and PERF-01 timing separation on a short closed-loop run."""

from __future__ import annotations

import json
import zipfile
from datetime import timedelta

import pytest

from aether import cli
from aether.cli import LineageError, main, verify_export, verify_lineage
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


@pytest.fixture(scope="module")
def pinned_bundle(base_config_path):
    loaded = load_scenario(base_config_path)
    assert loaded.model.sources.plume_dataset is not None
    return ScenarioBundle(model=_short(loaded.model), truth=_short(loaded.truth))


def _bytes(run: RunRecord) -> bytes:
    return run.model_dump_json().encode()


def _seeded(bundle, seed):
    """The bundle as the runner sees it: ``run_policy`` hashes the config with ``seed`` applied."""
    views = {}
    for name in ("model", "truth"):
        data = getattr(bundle, name).model_dump(mode="python")
        data["random_seed"] = seed
        views[name] = ScenarioConfig.model_validate(data)
    return ScenarioBundle(**views)


def _run_manifest(bundle, *, synthetic_only=False, seed=1000):
    bundle = _seeded(bundle, seed)
    root = cli._repo_root()
    inputs = [root / rel for rel in cli.PINNED_INPUTS] + cli._dataset_inputs(bundle)
    return cli._manifest(bundle, [], inputs, synthetic_only=synthetic_only)


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
    assert performance.windows_source == "computed"
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
    assert performance.windows_source == "process_cache"


def test_export_carries_performance_separately(bundle, tmp_path):
    run, performance = runner.run_policy_with_performance(bundle, "largest_first", 1000)
    run_dir = tmp_path / run.run_id
    run_dir.mkdir()
    (run_dir / "run.json").write_text(run.model_dump_json())
    (run_dir / "manifest.json").write_text(json.dumps(_run_manifest(bundle, synthetic_only=True)))
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


def test_window_key_ignores_family_and_seed_but_not_geometry(bundle):
    cfg = bundle.model
    sources, _ = runner.resolve_sources(cfg, 1000)
    start = cfg.simulation_epoch_utc
    end = start + timedelta(hours=cfg.horizon_hours)
    data = cfg.model_dump(mode="python")
    data["family"], data["random_seed"] = "m1_persistence_wrong", 7
    relabelled = ScenarioConfig.model_validate(data)
    data["window_search"]["option_step_s"] = 20.0
    regridded = ScenarioConfig.model_validate(data)
    key = runner._window_cache_key(cfg, sources, start, end)
    assert runner._window_cache_key(relabelled, sources, start, end) == key
    assert runner._window_cache_key(regridded, sources, start, end) != key
    assert runner._window_cache_key(cfg, sources[1:], start, end) != key


def test_disk_window_cache_gives_identical_records(bundle, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "_WINDOW_CACHE", {})
    monkeypatch.delenv(runner.WINDOW_CACHE_ENV, raising=False)
    reference = runner.run_policy(bundle, "greedy_eig", 1000)

    monkeypatch.setenv(runner.WINDOW_CACHE_ENV, str(tmp_path / "cache"))
    monkeypatch.setattr(runner, "_WINDOW_CACHE", {})
    written, perf_written = runner.run_policy_with_performance(bundle, "greedy_eig", 1000)
    assert perf_written.windows_source == "computed"
    assert len(list((tmp_path / "cache").glob("windows-*.json"))) == 1
    assert not list((tmp_path / "cache").glob("*.tmp"))

    monkeypatch.setattr(runner, "_WINDOW_CACHE", {})
    loaded, perf_loaded = runner.run_policy_with_performance(bundle, "greedy_eig", 1000)
    assert perf_loaded.windows_source == "disk_cache"
    assert _bytes(reference) == _bytes(written) == _bytes(loaded)


def test_pinned_run_lineage_exports_and_reloads(pinned_bundle, tmp_path):
    run, performance = runner.run_policy_with_performance(pinned_bundle, "largest_first", 1000)
    ref = run.input_dataset
    assert ref is not None and ref.dataset_id == "emit-l2b-ch4plm-002-permian-v1"
    assert (ref.seeded_source_count, ref.uniform_fill_count) == (6, 0)
    assert run.sources == runner.resolve_sources(pinned_bundle.model, 1000)[0]
    manifest = _run_manifest(pinned_bundle)
    dataset_files = cli._dataset_inputs(pinned_bundle)
    assert len(dataset_files) == 42  # manifest + normalized + 20 metadata/raster pairs
    assert len(manifest["input_sha256"]) == len(cli.PINNED_INPUTS) + 42
    assert all(not key.startswith("/") for key in manifest["input_sha256"])
    assert manifest["input_dataset"]["manifest_sha256"] == ref.manifest_sha256

    run_dir = tmp_path / run.run_id
    run_dir.mkdir()
    (run_dir / "run.json").write_text(run.model_dump_json())
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    (run_dir / "performance.json").write_text(performance.model_dump_json())
    output = tmp_path / "pinned.zip"
    args = ["export", "--run-dir", str(tmp_path), "--run-id", run.run_id, "--output", str(output)]
    assert main(args) == 0
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    assert "inputs/data/manifests/emit_permian.json" in names
    assert "inputs/data/normalized/emit_permian_plumes.json" in names
    summary = verify_export(output)
    assert summary["dataset_files"] == 42 and summary["input_dataset"] == ref.dataset_id

    raw_key = next(k for k in manifest["input_sha256"] if k.endswith(".tif"))
    dropped = json.loads(json.dumps(manifest))
    del dropped["input_sha256"][raw_key]
    with pytest.raises(LineageError, match="lacks required evidence"):
        verify_lineage(dropped, run)

    root = cli._repo_root()
    for rel in manifest["input_sha256"]:
        (tmp_path / "copy" / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "copy" / rel).write_bytes((root / rel).read_bytes())
    assert verify_lineage(manifest, run, root=tmp_path / "copy")["dataset_files"] == 42
    raster = tmp_path / "copy" / raw_key
    raster.write_bytes(raster.read_bytes() + b"\0")
    with pytest.raises(LineageError, match="altered"):
        verify_lineage(manifest, run, root=tmp_path / "copy")
