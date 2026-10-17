"""Paired statistics for the benchmark (EVL-03, PR-E04, PR-E05, PR-E06; PRD 9.4).

All differences are ``a - b`` per seed. For Brier-type scores (lower is better) a negative mean
difference favours ``a``. Every random draw comes from ``aether.rng`` namespace ``"bootstrap"``,
keyed by a comparison id, so a CI is reproducible and independent of the order comparisons run.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

from aether.rng import keyed_rng


@dataclass(frozen=True)
class PairedBootstrap:
    mean_diff: float
    lo: float
    hi: float
    p_value: float  # two-sided bootstrap p for H0: mean difference = 0
    n: int
    resamples: int
    level: float

    @property
    def excludes_zero(self) -> bool:
        return self.lo > 0.0 or self.hi < 0.0


def _paired(a: Sequence[float], b: Sequence[float]) -> np.ndarray:
    if len(a) != len(b):
        raise ValueError(f"paired samples differ in length: {len(a)} vs {len(b)}")
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    if not np.all(np.isfinite(d)):
        raise ValueError("paired differences must be finite (drop undefined seeds first)")
    return d


def paired_bootstrap(
    scores_a: Sequence[float],
    scores_b: Sequence[float],
    resamples: int,
    level: float,
    seed: int,
    comparison_id: str = "",
) -> PairedBootstrap:
    """Percentile bootstrap CI of the mean paired difference, resampling seeds with replacement.

    The p-value is ``2 * min(P*(D <= 0), P*(D >= 0))`` with the +1 correction, so it is never 0
    and the percentile CI at ``level`` excludes 0 roughly when ``p < 1 - level``.
    """
    d = _paired(scores_a, scores_b)
    n = len(d)
    if n < 2:
        raise ValueError("paired bootstrap needs at least 2 paired seeds")
    if not 0 < level < 1:
        raise ValueError("level must be in (0, 1)")
    rng = keyed_rng(seed, "bootstrap", comparison_id)
    means = d[rng.integers(0, n, size=(resamples, n))].mean(axis=1)
    alpha = 1.0 - level
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    below = (np.count_nonzero(means <= 0) + 1) / (resamples + 1)
    above = (np.count_nonzero(means >= 0) + 1) / (resamples + 1)
    return PairedBootstrap(
        mean_diff=float(d.mean()),
        lo=float(lo),
        hi=float(hi),
        p_value=float(min(1.0, 2 * min(below, above))),
        n=n,
        resamples=resamples,
        level=level,
    )


@dataclass(frozen=True)
class HolmResult:
    adjusted_p: float
    reject: bool


def holm(p_values: Mapping[str, float], alpha: float = 0.05) -> dict[str, HolmResult]:
    """Holm-Bonferroni step-down. Adjusted p values are monotone and capped at 1."""
    order = sorted(p_values, key=lambda k: (p_values[k], k))
    m = len(order)
    out: dict[str, HolmResult] = {}
    running = 0.0
    for i, key in enumerate(order):
        running = max(running, min(1.0, (m - i) * p_values[key]))
        out[key] = HolmResult(adjusted_p=running, reject=running < alpha)
    return out


@dataclass(frozen=True)
class SuccessVerdict:
    success: bool
    m0_win: bool
    misspecified_wins: tuple[str, ...]
    zero_violations: bool
    reasons: tuple[str, ...]


def success_verdict(
    primary: Mapping[str, PairedBootstrap],
    total_checker_violations: int,
    control_family: str = "m0_well_specified",
    misspecified_families: Sequence[str] = (
        "m1_persistence_wrong",
        "m2_pod_optimistic",
        "m3_forecast_overconfident",
        "m4_false_positives",
    ),
    alpha: float = 0.05,
    required_misspecified_wins: int = 2,
) -> SuccessVerdict:
    """PR-E05 / protocol ``success_criterion``, primary comparison (adaptive - largest_first).

    A family counts as a win only when the mean paired Brier difference is negative. m0 needs a CI
    excluding 0; misspecified families need a Holm-adjusted rejection at family-wise ``alpha``.
    """
    reasons = []
    if control_family not in primary:
        raise KeyError(f"missing control family {control_family}")
    m0 = primary[control_family]
    m0_win = m0.mean_diff < 0 and m0.hi < 0
    if not m0_win:
        reasons.append(f"{control_family}: CI [{m0.lo:.4g}, {m0.hi:.4g}] does not lie below 0")
    present = [f for f in misspecified_families if f in primary]
    missing = sorted(set(misspecified_families) - set(present))
    if missing:
        reasons.append(f"families not run: {missing}")
    adj = holm({f: primary[f].p_value for f in present}, alpha)
    wins = tuple(f for f in present if adj[f].reject and primary[f].mean_diff < 0)
    if len(wins) < required_misspecified_wins:
        reasons.append(
            f"{len(wins)} misspecified wins after Holm, need {required_misspecified_wins}"
        )
    zero = total_checker_violations == 0
    if not zero:
        reasons.append(f"{total_checker_violations} feasibility-checker violations")
    ok = m0_win and len(wins) >= required_misspecified_wins and zero
    return SuccessVerdict(ok, m0_win, wins, zero, tuple(reasons))


# --- Discriminability gate G4.5 (PR-E06) ---------------------------------------------------------


@dataclass(frozen=True)
class GateResult:
    passed: bool
    gap: float  # mean(random - oracle) Brier; positive when the oracle is better
    sd_paired: float  # sample SD of the per-seed paired difference
    n_seeds: int
    rule: str


def discriminability_gate(
    oracle_brier: Sequence[float], random_brier: Sequence[float]
) -> GateResult:
    """Protocol rule: oracle-minus-random Brier gap > 2 x SD of the paired difference across seeds.

    The rule uses the per-seed SD (not the standard error), so it asks that the bounds separate on
    almost every seed, not just on average.
    """
    d = _paired(random_brier, oracle_brier)
    if len(d) < 2:
        raise ValueError("gate needs at least 2 tuning seeds")
    gap = float(d.mean())
    sd = float(d.std(ddof=1))
    return GateResult(
        passed=gap > 2.0 * sd,
        gap=gap,
        sd_paired=sd,
        n_seeds=len(d),
        rule="mean(random - oracle) > 2 * sd(random - oracle)",
    )


def seeds_for_power(
    sd_paired: float, min_effect: float, alpha: float = 0.05, power: float = 0.8
) -> int:
    """Normal-approximation seed count for a two-sided paired test (protocol ``seed_count_rule``).

    ``min_effect`` is the pre-stated minimum Brier difference worth detecting. It must be fixed
    before holdout runs; the protocol does not state it yet (see docs/validation-report.md).
    """
    if sd_paired < 0 or min_effect <= 0:
        raise ValueError("need sd_paired >= 0 and min_effect > 0")
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    return max(2, math.ceil((z * sd_paired / min_effect) ** 2))
