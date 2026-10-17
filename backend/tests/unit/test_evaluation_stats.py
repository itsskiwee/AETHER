"""EVL-03 bootstrap coverage, Holm, success verdict and the G4.5 gate."""

import numpy as np
import pytest

from aether.evaluation.stats import (
    PairedBootstrap,
    discriminability_gate,
    holm,
    paired_bootstrap,
    seeds_for_power,
    success_verdict,
)
from aether.rng import keyed_rng


def test_bootstrap_is_reproducible_and_keyed():
    data = keyed_rng(0, "bootstrap", "repro-test-data")
    a, b = data.normal(0.2, 0.05, 25), data.normal(0.21, 0.05, 25)
    r1 = paired_bootstrap(a, b, 2000, 0.95, seed=7, comparison_id="m0|x-y")
    r2 = paired_bootstrap(a, b, 2000, 0.95, seed=7, comparison_id="m0|x-y")
    r3 = paired_bootstrap(a, b, 2000, 0.95, seed=7, comparison_id="m1|x-y")
    assert r1 == r2
    assert (r1.lo, r1.hi) != (r3.lo, r3.hi)
    assert r1.mean_diff == pytest.approx(np.mean(np.subtract(a, b)))


def test_bootstrap_ci_covers_true_difference_about_95_percent():
    """EVL-03 acceptance: 200 trials with a known effect; coverage should be near 0.95.

    Percentile bootstrap under-covers slightly at n = 30; the band allows that plus Monte Carlo
    error (binomial SD at 200 trials is ~1.5 points).
    """
    true_diff, n, trials = -0.02, 30, 200
    hits = 0
    for trial in range(trials):
        rng = keyed_rng(trial, "bootstrap", "coverage-test-data")
        b = rng.normal(0.2, 0.03, n)
        a = b + true_diff + rng.normal(0.0, 0.01, n)
        res = paired_bootstrap(a, b, 2000, 0.95, seed=trial, comparison_id="coverage")
        hits += res.lo <= true_diff <= res.hi
    assert 0.89 <= hits / trials <= 0.99


def test_bootstrap_p_value_agrees_with_ci():
    a = np.linspace(0.10, 0.20, 20)
    clear = paired_bootstrap(a, a + 0.05, 5000, 0.95, seed=1)
    assert clear.excludes_zero and clear.p_value < 0.05
    noise = keyed_rng(3, "bootstrap", "noise").normal(0, 0.05, 20)
    null = paired_bootstrap(a + noise, a, 5000, 0.95, seed=1)
    assert null.excludes_zero == (null.p_value < 0.05)


def test_bootstrap_rejects_bad_input():
    with pytest.raises(ValueError):
        paired_bootstrap([0.1], [0.2], 100, 0.95, seed=0)
    with pytest.raises(ValueError):
        paired_bootstrap([0.1, 0.2], [0.2], 100, 0.95, seed=0)
    with pytest.raises(ValueError):
        paired_bootstrap([0.1, float("nan")], [0.2, 0.3], 100, 0.95, seed=0)


def test_holm_matches_hand_computation():
    # sorted p: 0.01 (x4 = 0.04), 0.02 (x3 = 0.06), 0.03 (x2 = 0.06), 0.5 (x1 = 0.5)
    res = holm({"a": 0.03, "b": 0.01, "c": 0.5, "d": 0.02}, alpha=0.05)
    assert {k: round(v.adjusted_p, 10) for k, v in res.items()} == {
        "b": 0.04,
        "d": 0.06,
        "a": 0.06,
        "c": 0.5,
    }
    assert [k for k, v in res.items() if v.reject] == ["b"]


def _pb(mean, lo, hi, p):
    return PairedBootstrap(mean, lo, hi, p, n=30, resamples=10000, level=0.95)


def test_success_requires_m0_and_two_holm_wins_and_zero_violations():
    primary = {
        "m0_well_specified": _pb(-0.01, -0.02, -0.001, 0.01),
        "m1_persistence_wrong": _pb(-0.01, -0.02, -0.005, 0.001),
        "m2_pod_optimistic": _pb(-0.01, -0.02, -0.005, 0.002),
        "m3_forecast_overconfident": _pb(0.01, 0.0, 0.02, 0.04),
        "m4_false_positives": _pb(-0.001, -0.01, 0.01, 0.6),
    }
    v = success_verdict(primary, total_checker_violations=0)
    assert v.success and v.misspecified_wins == ("m1_persistence_wrong", "m2_pod_optimistic")
    assert not success_verdict(primary, total_checker_violations=1).success
    lost_m0 = primary | {"m0_well_specified": _pb(-0.01, -0.02, 0.001, 0.08)}
    assert not success_verdict(lost_m0, 0).success


def test_success_ignores_significant_losses():
    primary = {
        "m0_well_specified": _pb(-0.01, -0.02, -0.001, 0.01),
        "m1_persistence_wrong": _pb(0.02, 0.01, 0.03, 0.001),  # significant, wrong direction
        "m2_pod_optimistic": _pb(0.02, 0.01, 0.03, 0.001),
        "m3_forecast_overconfident": _pb(-0.01, -0.02, -0.005, 0.001),
        "m4_false_positives": _pb(0.0, -0.01, 0.01, 0.9),
    }
    v = success_verdict(primary, 0)
    assert not v.success and v.misspecified_wins == ("m3_forecast_overconfident",)


def test_gate():
    oracle = [0.10, 0.11, 0.09, 0.10]
    assert discriminability_gate(oracle, [0.20, 0.21, 0.19, 0.20]).passed
    noisy = discriminability_gate(oracle, [0.30, 0.10, 0.12, 0.11])
    assert noisy.gap > 0 and not noisy.passed


def test_seeds_for_power():
    # z = 1.95996 + 0.84162 = 2.80158; (2.80158 * 0.02 / 0.01)^2 = 31.4 -> 32
    assert seeds_for_power(0.02, 0.01) == 32
    with pytest.raises(ValueError):
        seeds_for_power(0.02, 0.0)
