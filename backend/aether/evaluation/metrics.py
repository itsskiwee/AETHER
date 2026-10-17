"""Truth-based metrics for one policy run (EVL-01, EVL-02; PRD 9.2, experiments/protocol.yaml).

RESTRICTED: reads ``TruthHistory``. Only ``aether.evaluation`` and ``aether.simulation`` may import
this module's inputs. Nothing here is visible to a policy during a run.

Conventions (decisions recorded in docs/validation-report.md, "Metric definitions"):

- Evaluation times are ``t0 + k * eval_interval_hours`` for every k with ``k * interval < horizon``
  (PR-E01). The truth state at time t is the hour cell containing t.
- At each evaluation time the run must contain a ``BeliefSnapshot`` for every source with exactly
  that ``state_time_utc``. A missing snapshot raises: silently reusing a stale belief would score a
  policy on information it never had.
- If several snapshots share (source, time), the last one in ``run.beliefs`` order is used (the
  post-update belief).
- Undefined metrics (empty denominators) are ``None``, never 0 or NaN. Their denominators are
  always reported next to them.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from aether.config import ScenarioConfig
from aether.contracts.enums import ObservationOutcome, ProvenanceClass, Regime
from aether.contracts.models import BeliefSnapshot, RunRecord
from aether.simulation.truth_types import TruthHistory

EVIDENCE_OUTCOMES = frozenset(
    {ObservationOutcome.DETECTION, ObservationOutcome.VALID_NON_DETECTION}
)
LOG_LOSS_CLIP = 1e-12  # PR-E08
ECE_BINS = 10  # PR-E09
HIGH_IMPACT_TOP_K = 5  # PR-E10

Score = float | int | None


@dataclass(frozen=True)
class _Point:
    """One (source, evaluation time) pair."""

    source_id: str
    hours_from_t0: float
    p_active: float
    z_true: int
    flux_ci90_kg_h: tuple[float, float]


def evaluation_times(
    epoch_utc: datetime, horizon_hours: float, interval_hours: float
) -> list[datetime]:
    """PR-E01: every ``interval_hours`` from t0, strictly before the horizon."""
    if interval_hours <= 0:
        raise ValueError("interval_hours must be positive")
    times = []
    k = 0
    while k * interval_hours < horizon_hours:
        times.append(epoch_utc + timedelta(hours=k * interval_hours))
        k += 1
    return times


def _belief_index(beliefs: Iterable[BeliefSnapshot]) -> dict[tuple[str, datetime], BeliefSnapshot]:
    index: dict[tuple[str, datetime], BeliefSnapshot] = {}
    for b in beliefs:
        index[(b.source_id, b.state_time_utc)] = b  # later snapshots overwrite earlier ones
    return index


def _check_inputs(run: RunRecord, truth: TruthHistory, cfg: ScenarioConfig) -> None:
    if truth.provenance_class is not ProvenanceClass.SIMULATED_GROUND_TRUTH:
        raise ValueError("truth must be SIMULATED_GROUND_TRUTH")
    run_ids = {s.id for s in run.sources}
    if run_ids != set(truth.sources):
        raise ValueError(
            "run and truth disagree on sources: "
            f"only in run {sorted(run_ids - set(truth.sources))}, "
            f"only in truth {sorted(set(truth.sources) - run_ids)}"
        )
    if truth.hours != round(cfg.horizon_hours):
        raise ValueError(
            f"truth covers {truth.hours} h but config horizon is {cfg.horizon_hours} h"
        )
    if truth.epoch_utc != cfg.simulation_epoch_utc:
        raise ValueError("truth epoch differs from config simulation epoch")


def _collect_points(run: RunRecord, truth: TruthHistory, times: Sequence[datetime]) -> list[_Point]:
    index = _belief_index(run.beliefs)
    points = []
    for t in times:
        h = truth.hour_index(t)
        hours = (t - truth.epoch_utc).total_seconds() / 3600.0
        for sid in sorted(truth.sources):
            snap = index.get((sid, t))
            if snap is None:
                raise ValueError(
                    f"run {run.run_id} has no belief snapshot for {sid} at {t.isoformat()}"
                )
            points.append(
                _Point(
                    source_id=sid,
                    hours_from_t0=hours,
                    p_active=float(snap.p_active),
                    z_true=int(bool(truth.sources[sid].active[h])),
                    flux_ci90_kg_h=snap.flux_ci90_kg_h,
                )
            )
    return points


# --- Probabilistic scores of the binary active state ---------------------------------------------


def brier(points: Sequence[_Point]) -> float | None:
    if not points:
        return None
    return float(np.mean([(p.p_active - p.z_true) ** 2 for p in points]))


def log_loss(points: Sequence[_Point]) -> float | None:
    """Mean negative log-likelihood in nats, probabilities clipped to [PR-E08, 1 - PR-E08]."""
    if not points:
        return None
    p = np.clip([pt.p_active for pt in points], LOG_LOSS_CLIP, 1.0 - LOG_LOSS_CLIP)
    z = np.array([pt.z_true for pt in points], dtype=float)
    return float(-np.mean(z * np.log(p) + (1.0 - z) * np.log(1.0 - p)))


def ece(points: Sequence[_Point], bins: int = ECE_BINS) -> float | None:
    """Expected calibration error, equal-width bins weighted by count. p = 1 is in the top bin."""
    if not points:
        return None
    p = np.array([pt.p_active for pt in points])
    z = np.array([pt.z_true for pt in points], dtype=float)
    idx = np.minimum((p * bins).astype(int), bins - 1)
    total = 0.0
    for b in range(bins):
        mask = idx == b
        if mask.any():
            total += mask.sum() / len(p) * abs(p[mask].mean() - z[mask].mean())
    return float(total)


# --- Flux interval coverage ----------------------------------------------------------------------


def flux_interval_coverage(points: Sequence[_Point], truth: TruthHistory) -> float | None:
    """Fraction of (source, time) pairs whose 90% interval contains the source's true static flux.

    The belief's flux variable is the static per-source flux Q_i (belief/__init__.py), defined
    whether or not the source is active, so it is compared with ``SourceTruth.median_flux_kg_h``
    at every evaluation time.
    """
    if not points:
        return None
    hits = [
        pt.flux_ci90_kg_h[0] <= truth.sources[pt.source_id].median_flux_kg_h <= pt.flux_ci90_kg_h[1]
        for pt in points
    ]
    return float(np.mean(hits))


# --- Corroboration (EVL-02) ----------------------------------------------------------------------


@dataclass(frozen=True)
class Corroboration:
    """Per-source first corroboration time (PR-E03). ``None`` = right-censored at the horizon."""

    hours_by_source: dict[str, float | None]
    horizon_hours: float

    @property
    def corroborated(self) -> int:
        return sum(v is not None for v in self.hours_by_source.values())

    @property
    def censored(self) -> int:
        return sum(v is None for v in self.hours_by_source.values())

    def restricted_mean_hours(self) -> float | None:
        """Restricted mean time to corroboration: censored sources count as the full horizon."""
        if not self.hours_by_source:
            return None
        return float(
            np.mean([self.horizon_hours if v is None else v for v in self.hours_by_source.values()])
        )


def corroboration(
    points: Sequence[_Point], threshold: float, horizon_hours: float
) -> Corroboration:
    """First evaluation time at which P(Z = z_true) >= threshold. Never-corroborated -> censored."""
    out: dict[str, float | None] = {}
    for pt in sorted(points, key=lambda p: (p.source_id, p.hours_from_t0)):
        out.setdefault(pt.source_id, None)
        if out[pt.source_id] is not None:
            continue
        p_true_state = pt.p_active if pt.z_true else 1.0 - pt.p_active
        if p_true_state >= threshold:
            out[pt.source_id] = pt.hours_from_t0
    return Corroboration(hours_by_source=out, horizon_hours=horizon_hours)


# --- High-impact identification ------------------------------------------------------------------


def high_impact_sources(truth: TruthHistory, threshold_kg_h: float) -> set[str]:
    """PR-E02: true mean emission rate over the horizon (inactive hours count as 0) >= threshold."""
    return {
        sid
        for sid, s in truth.sources.items()
        if float(np.sum(s.flux_kg_h)) / truth.hours >= threshold_kg_h
    }


def expected_mean_rate_kg_h(snap: BeliefSnapshot, cfg: ScenarioConfig) -> float:
    """Planner-side estimate of a source's long-run mean rate: sum_r P(r) * pi_r * median flux.

    pi_r is the stationary active fraction of regime r under the MODEL config. This ranks by the
    same quantity PR-E02 thresholds (a long-run mean rate), not by the instantaneous state.
    """
    stationary = {r.name: r.stationary_p_active for r in cfg.sources.regimes}
    p_long_run = sum(prob * stationary[Regime(reg)] for reg, prob in snap.regime_probs.items())
    return p_long_run * snap.flux_median_kg_h


def high_impact_recall_at_k(
    run: RunRecord,
    truth: TruthHistory,
    cfg: ScenarioConfig,
    at_utc: datetime,
    k: int = HIGH_IMPACT_TOP_K,
) -> tuple[float | None, int]:
    """Recall of high-impact sources in the top-k by ``expected_mean_rate_kg_h`` at ``at_utc``.

    Returns (recall, number of high-impact sources). Recall is ``None`` when there are none; the
    protocol excludes those seeds and reports how many were excluded. Ties break by source id.
    """
    hi = high_impact_sources(truth, cfg.evaluation.high_impact_mean_rate_kg_h)
    if not hi:
        return None, 0
    index = _belief_index(run.beliefs)
    scored = []
    for sid in sorted(truth.sources):
        snap = index.get((sid, at_utc))
        if snap is None:
            raise ValueError(
                f"run {run.run_id} has no belief snapshot for {sid} at {at_utc.isoformat()}"
            )
        scored.append((-expected_mean_rate_kg_h(snap, cfg), sid))
    top = {sid for _, sid in sorted(scored)[:k]}
    return len(top & hi) / len(hi), len(hi)


# --- Acquisition, solver and checker accounting --------------------------------------------------


def acquisition_counts(run: RunRecord) -> dict[str, Score]:
    attempted = [a for a in run.acquisitions if a.outcome is not ObservationOutcome.NOT_OBSERVED]
    valid = [a for a in attempted if a.outcome in EVIDENCE_OUTCOMES]
    return {
        "acquisitions_count": len(attempted),
        "valid_acquisitions_count": len(valid),
        "valid_acquisition_fraction": len(valid) / len(attempted) if attempted else None,
        "not_observed_records": len(run.acquisitions) - len(attempted),
    }


def solver_and_checker(run: RunRecord) -> dict[str, Score]:
    runtimes = [p.runtime_s for p in run.plans]
    validated = {v.plan_revision: v for v in run.validations}
    return {
        "plans_count": len(run.plans),
        "solver_runtime_p95_s": float(np.percentile(runtimes, 95)) if runtimes else None,
        "feasibility_checker_violations": sum(len(v.violations) for v in run.validations),
        "plans_failing_validation": sum(not v.ok for v in run.validations),
        "plans_without_validation": sum(p.revision not in validated for p in run.plans),
    }


def observed_sources(run: RunRecord) -> set[str]:
    """Sources with at least one evidence-bearing acquisition (DETECTION or VALID_NON_DETECTION)."""
    return {a.source_id for a in run.acquisitions if a.outcome in EVIDENCE_OUTCOMES}


# --- Run score -----------------------------------------------------------------------------------


def _probabilistic(
    prefix_suffix: str, points: Sequence[_Point], truth: TruthHistory
) -> dict[str, Score]:
    return {
        f"brier_active_state{prefix_suffix}": brier(points),
        f"log_loss_active_state{prefix_suffix}": log_loss(points),
        f"ece_active_state{prefix_suffix}": ece(points),
        f"flux_interval_coverage_90{prefix_suffix}": flux_interval_coverage(points, truth),
        f"n_points{prefix_suffix}": len(points),
        f"n_sources{prefix_suffix}": len({p.source_id for p in points}),
    }


def score_run(run: RunRecord, truth: TruthHistory, cfg: ScenarioConfig) -> dict[str, Score]:
    """Score one run against its hidden truth. ``cfg`` is the MODEL view (``bundle.model``).

    Keys follow ``experiments/protocol.yaml``. Breakdowns use the suffixes ``[regime=<R>]`` and
    ``[observed=<yes|no>]``. Every rate comes with its denominator.
    """
    _check_inputs(run, truth, cfg)
    ev = cfg.evaluation
    times = evaluation_times(truth.epoch_utc, truth.hours, ev.eval_interval_hours)
    points = _collect_points(run, truth, times)

    scores: dict[str, Score] = {"n_evaluation_times": len(times)}
    scores |= _probabilistic("", points, truth)

    for regime in Regime:
        subset = [p for p in points if truth.sources[p.source_id].regime is regime]
        scores |= _probabilistic(f"[regime={regime.value}]", subset, truth)

    seen = observed_sources(run)
    for label, keep in (("yes", True), ("no", False)):
        subset = [p for p in points if (p.source_id in seen) == keep]
        scores |= _probabilistic(f"[observed={label}]", subset, truth)

    corr = corroboration(points, ev.corroboration_p_threshold, float(truth.hours))
    scores["time_to_corroboration_hours"] = corr.restricted_mean_hours()
    scores["corroborated_sources"] = corr.corroborated
    scores["censored_sources"] = corr.censored

    recall, n_hi = high_impact_recall_at_k(run, truth, cfg, times[-1])
    scores["high_impact_recall_at_5"] = recall
    scores["n_high_impact_sources"] = n_hi

    scores |= acquisition_counts(run)
    scores |= solver_and_checker(run)
    return scores
