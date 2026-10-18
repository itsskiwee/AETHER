"""DATA-02: pinned plume dataset in config, source resolution and run provenance."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import aether.ingestion
from aether.config import ScenarioBundle, ScenarioConfig, load_scenario
from aether.contracts.models import DataSource, InputDatasetRef, PlumeObservation
from aether.simulation import runner

SHA_A = "a" * 64
SHA_B = "b" * 64
T0 = datetime(2023, 9, 1, 17, tzinfo=UTC)


def _with_dataset(cfg: ScenarioConfig, dataset: dict | None) -> ScenarioConfig:
    data = cfg.model_dump(mode="python")
    data["sources"]["plume_dataset"] = dataset
    return ScenarioConfig.model_validate(data)


def _plume(native_id: str, lon: float, lat: float, rate: float | None) -> PlumeObservation:
    source = DataSource(
        provider="NASA LP DAAC",
        dataset="EMITL2BCH4PLM",
        version="002",
        url="https://example.invalid/test",
        license_url=None,
        citation_text="test record",
        retrieved_at_utc=T0,
        sha256=SHA_B,
    )
    return PlumeObservation(
        id=f"emit:{native_id}",
        provider=source.provider,
        native_id=native_id,
        dataset_version="002",
        acquisition_time_utc=T0,
        lon=lon,
        lat=lat,
        geometry_geojson=None,
        acquisition_id=None,
        emission_rate_kg_h=rate,
        emission_rate_uncertainty_kg_h=None,
        missing_rate_reason=None if rate is not None else "NOT_PROVIDED",
        raw_properties={},
        source=source,
    )


PLUMES = (
    _plume("a", -103.0, 32.0, 900.0),
    _plume("b", -103.0005, 32.0, None),  # ~47 m from "a": one cluster
    _plume("c", -101.5, 33.0, None),
    _plume("outside", -90.0, 32.0, 500.0),
)


@pytest.fixture
def pinned(monkeypatch, base_config_path):
    """A config naming a dataset, with a fake verified loader standing in for aether.ingestion."""
    calls = []

    def fake_loader(path, *, expected_manifest_sha256, repo_root):
        calls.append((path, expected_manifest_sha256, repo_root))
        return SimpleNamespace(
            dataset_id="test-dataset",
            manifest_sha256=expected_manifest_sha256,
            normalized_sha256=SHA_B,
            plumes=PLUMES,
        )

    monkeypatch.setattr(aether.ingestion, "load_pinned_plume_dataset", fake_loader, raising=False)
    monkeypatch.setattr(runner, "_DATASET_CACHE", {})
    cfg = _with_dataset(
        load_scenario(base_config_path, synthetic_only=True).model,
        {"manifest": "data/manifests/test.json", "manifest_sha256": SHA_A},
    )
    return cfg, calls


@pytest.mark.parametrize(
    "manifest", ["/abs/manifest.json", "../outside.json", "data/../x.json", "", "data\\m.json"]
)
def test_dataset_manifest_must_be_repo_relative(base_config_path, manifest):
    cfg = load_scenario(base_config_path, synthetic_only=True).model
    with pytest.raises(ValidationError):
        _with_dataset(cfg, {"manifest": manifest, "manifest_sha256": SHA_A})


def test_dataset_hash_is_required_and_bound_into_config_hash(base_config_path):
    cfg = load_scenario(base_config_path, synthetic_only=True).model
    with pytest.raises(ValidationError):
        _with_dataset(cfg, {"manifest": "data/m.json", "manifest_sha256": "nothex"})
    one = _with_dataset(cfg, {"manifest": "data/m.json", "manifest_sha256": SHA_A})
    two = _with_dataset(cfg, {"manifest": "data/m.json", "manifest_sha256": SHA_B})
    assert len({cfg.config_hash(), one.config_hash(), two.config_hash()}) == 3


def test_dataset_requires_plume_placement(base_config_path):
    data = load_scenario(base_config_path, synthetic_only=True).model.model_dump(mode="python")
    data["sources"]["placement"] = "uniform"
    data["sources"]["plume_dataset"] = {"manifest": "data/m.json", "manifest_sha256": SHA_A}
    with pytest.raises(ValidationError, match="placement"):
        ScenarioConfig.model_validate(data)


def test_truth_view_cannot_name_a_different_dataset(base_config_path):
    cfg = load_scenario(base_config_path, synthetic_only=True).model
    other = _with_dataset(cfg, {"manifest": "data/m.json", "manifest_sha256": SHA_A})
    with pytest.raises(ValidationError, match="plume_dataset"):
        ScenarioBundle(model=cfg, truth=other)


def test_synthetic_only_clears_both_views(base_config_path, scenarios_dir):
    family = sorted(scenarios_dir.glob("m1_*.yaml"))[0]
    bundle = load_scenario(base_config_path, family, synthetic_only=True)
    assert bundle.model.sources.plume_dataset is None
    assert bundle.truth.sources.plume_dataset is None


def test_synthetic_only_sources_have_no_dataset_ref(base_config_path):
    cfg = load_scenario(base_config_path, synthetic_only=True).model
    sources, ref = runner.resolve_sources(cfg, 1000)
    assert ref is None
    assert len(sources) == cfg.sources.count
    assert all(source.seeded_from_plume_id is None for source in sources)


def test_configured_dataset_seeds_sources_and_reports_counts(pinned, repo_root):
    cfg, calls = pinned
    sources, ref = runner.resolve_sources(cfg, 1000)
    assert calls == [(repo_root / "data/manifests/test.json", SHA_A, repo_root)]
    seeded = {s.seeded_from_plume_id for s in sources if s.seeded_from_plume_id}
    assert seeded == {"emit:a", "emit:c"}  # one cluster for a+b; "outside" is out of region
    assert ref == InputDatasetRef(
        dataset_id="test-dataset",
        manifest_path="data/manifests/test.json",
        manifest_sha256=SHA_A,
        normalized_sha256=SHA_B,
        record_count=4,
        in_region_count=3,
        seeded_source_count=2,
        uniform_fill_count=cfg.sources.count - 2,
    )


def test_sources_are_deterministic_and_loaded_once(pinned):
    cfg, calls = pinned
    first = runner.resolve_sources(cfg, 1000)
    second = runner.resolve_sources(cfg, 1000)
    assert first == second
    assert len(calls) == 1
    # Seeded locations do not move with the seed; uniform fill does.
    other, _ = runner.resolve_sources(cfg, 1001)
    seeded = [s for s in first[0] if s.seeded_from_plume_id]
    assert seeded == [s for s in other if s.seeded_from_plume_id]
    assert first[0] != other


def test_explicit_plumes_conflict_with_configured_dataset(pinned):
    cfg, _ = pinned
    with pytest.raises(ValueError, match="do not also pass"):
        runner.resolve_sources(cfg, 1000, PLUMES)
    with pytest.raises(ValueError, match="do not also pass"):
        runner.resolve_sources(cfg, 1000, ())


def test_loader_failure_is_not_a_silent_fallback(monkeypatch, base_config_path):
    def broken(*_args, **_kwargs):
        raise ValueError("manifest hash mismatch")

    monkeypatch.setattr(aether.ingestion, "load_pinned_plume_dataset", broken, raising=False)
    monkeypatch.setattr(runner, "_DATASET_CACHE", {})
    cfg = _with_dataset(
        load_scenario(base_config_path, synthetic_only=True).model,
        {"manifest": "data/manifests/test.json", "manifest_sha256": SHA_A},
    )
    with pytest.raises(ValueError, match="hash mismatch"):
        runner.resolve_sources(cfg, 1000)


def test_run_record_rejects_dataset_counts_that_disagree_with_sources(pinned):
    cfg, _ = pinned
    sources, ref = runner.resolve_sources(cfg, 1000)
    wrong = ref.model_copy(update={"seeded_source_count": 1, "uniform_fill_count": 19})
    from aether.contracts.models import RunRecord

    base = {
        "run_id": "r",
        "policy_id": "largest_first",
        "scenario_id": "s",
        "family": "m0_well_specified",
        "seed": 1,
        "model_config_hash": "h",
        "truth_config_hash": "h",
        "code_version": "0",
        "sources": sources,
        "windows": (),
        "plans": (),
        "validations": (),
        "utilities": (),
        "acquisitions": (),
        "beliefs": (),
        "events": (),
    }
    assert RunRecord(**base, input_dataset=ref).input_dataset == ref
    with pytest.raises(ValidationError, match="disagree"):
        RunRecord(**base, input_dataset=wrong)


def test_input_dataset_ref_count_order():
    with pytest.raises(ValidationError):
        InputDatasetRef(
            dataset_id="d",
            manifest_path="m",
            manifest_sha256=SHA_A,
            normalized_sha256=SHA_B,
            record_count=2,
            in_region_count=3,
            seeded_source_count=0,
            uniform_fill_count=0,
        )
