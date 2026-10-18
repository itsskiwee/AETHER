import math

import pytest
import yaml
from pydantic import ValidationError

from aether.config import RegimeConfig, SolverConfig, load_scenario

FAMILIES = [
    "m0_well_specified",
    "m1_persistence_wrong",
    "m2_pod_optimistic",
    "m3_forecast_overconfident",
    "m4_false_positives",
    "r1_resource_scarce",
    "h168_long_horizon",
]


def test_base_loads_and_is_well_specified(base_config_path):
    bundle = load_scenario(base_config_path)
    assert bundle.model.config_hash() == bundle.truth.config_hash()
    assert len(bundle.model.spacecraft) == 4
    assert all(sc.virtual for sc in bundle.model.spacecraft.values())


def test_benchmark_base_has_no_scripted_events(base_config_path, repo_root):
    """lessons.md 2.6: the demo's cloud event must never reach the benchmark."""
    protocol = yaml.safe_load((repo_root / "experiments" / "protocol.yaml").read_text())
    assert protocol["base_config"] == "configs/base.yaml"
    assert load_scenario(base_config_path).model.weather.injected_events == ()


def test_demo_extends_base_with_event(demo_config_path, base_config_path):
    demo = load_scenario(demo_config_path).model
    base = load_scenario(base_config_path).model
    assert len(demo.weather.injected_events) == 1
    assert demo.sources == base.sources and demo.planner == base.planner


def test_hash_is_stable(base_config_path):
    assert (
        load_scenario(base_config_path).model.config_hash()
        == load_scenario(base_config_path).model.config_hash()
    )


def test_seed_override_is_the_only_seed(base_config_path):
    """lessons.md 2.7: no sub-seeds in config; the run seed changes every stream."""
    a = load_scenario(base_config_path, seed=1000).model
    b = load_scenario(base_config_path, seed=1001).model
    assert a.random_seed == 1000 and a.config_hash() != b.config_hash()
    dumped = a.model_dump()
    assert "seed" not in dumped["weather"] and "random_seed" not in dumped["planner"]["solver"]


def test_regime_math(base_config_path):
    persistent = load_scenario(base_config_path).model.sources.regimes[0]
    assert math.isclose(persistent.stationary_p_active, 240 / (240 + 48))
    # Pass clusters are ~21 h apart (lessons.md 2.1); only PERSISTENT remembers that long.
    assert persistent.correlation_time_hours > 21


def test_regime_rejects_impossible_chain():
    with pytest.raises(ValidationError):
        RegimeConfig(name="EPISODIC", weight=1.0, mean_on_hours=1.5, mean_off_hours=1.5)


def test_reproducible_solver_requires_single_worker():
    with pytest.raises(ValidationError):
        SolverConfig(
            mode="reproducible",
            max_deterministic_time=30,
            num_workers=8,
            fast_mode_wall_time_seconds=10,
        )


def test_coarse_step_must_not_miss_short_windows(tmp_path, base_config_path):
    fam = tmp_path / "coarse.yaml"
    fam.write_text("family: coarse\noverrides:\n  window_search.coarse_step_s: 10.0\n")
    with pytest.raises(ValidationError):
        load_scenario(base_config_path, fam)


def test_pod_slope(base_config_path):
    pod = load_scenario(base_config_path).model.sensors["vs_a_point_source"].pod
    assert math.isclose(pod.logistic_slope, math.log(9) / math.log(2))


@pytest.mark.parametrize("family", FAMILIES)
def test_families_load(base_config_path, scenarios_dir, family):
    bundle = load_scenario(base_config_path, scenarios_dir / f"{family}.yaml")
    misspecified = family.startswith("m") and family != "m0_well_specified"
    assert (bundle.model.config_hash() != bundle.truth.config_hash()) == misspecified


def test_truth_override_leaves_model_untouched(base_config_path, scenarios_dir):
    bundle = load_scenario(base_config_path, scenarios_dir / "m2_pod_optimistic.yaml")
    assert bundle.model.sensors["vs_a_point_source"].pod.q50_ref_kg_h == 100.0
    assert bundle.truth.sensors["vs_a_point_source"].pod.q50_ref_kg_h == 200.0


def test_unknown_override_path_fails(tmp_path, base_config_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("family: bad\noverrides:\n  planner.not_a_field: 1\n")
    with pytest.raises(KeyError):
        load_scenario(base_config_path, bad)
