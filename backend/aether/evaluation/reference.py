"""Reference policies and the discriminability gate G4.5 (EVL-08, PR-E06).

``OraclePolicy`` READS TRUTH. It exists only to bound how much any scheduler could gain in a
scenario. It is never a competitor, never appears in benchmark tables, and only the simulation
runner (which already holds truth) may construct it.

It is an oracle-informed *greedy reference*, not a proven upper bound. It knows the true state at
each option's time, but it is still myopic and still bound by the same feasibility rules (it plans
through ``planning.greedy`` like every heuristic baseline). The validation report states this.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from aether.contracts.enums import PolicyId
from aether.contracts.models import Plan, RunRecord
from aether.evaluation.stats import GateResult, discriminability_gate
from aether.planning.context import PlanningContext
from aether.planning.greedy import build_heuristic_plan, greedy_insert
from aether.simulation.truth_types import TruthHistory


class OraclePolicy:
    """Greedy by p_valid * (p_now - z_true(t))^2: the squared error a valid look could remove."""

    policy_id = PolicyId.ORACLE

    def __init__(self, truth: TruthHistory) -> None:
        self._truth = truth

    def window_values(self, ctx: PlanningContext) -> dict[str, float]:
        p_now: Mapping[str, float] = ctx.p_active_by_source
        values = {}
        for w in ctx.windows:
            if not w.feasible or w.id not in ctx.utilities:
                continue
            t = w.options[0].start_utc
            z = int(bool(self._truth.sources[w.source_id].active[self._truth.hour_index(t)]))
            values[w.id] = ctx.utilities[w.id].p_valid_forecast * (p_now[w.source_id] - z) ** 2
        return values

    def plan(self, ctx: PlanningContext) -> Plan:
        values = self.window_values(ctx)
        order = sorted(values, key=lambda wid: (-values[wid], wid))
        selected, _ = greedy_insert(
            ctx.windows,
            order,
            ctx.utilities,
            ctx.cfg.spacecraft,
            ctx.cfg.planner,
            ctx.committed,
            ctx.committed_selections,
        )
        return build_heuristic_plan(
            run_id=ctx.run_id,
            policy_id=self.policy_id,
            revision=ctx.revision,
            created_at_sim_utc=ctx.now_utc,
            cause=ctx.cause,
            planner_cfg=ctx.cfg.planner,
            windows=ctx.windows,
            selections=selected,
        )


# --- Capacity / demand diagnostics ---------------------------------------------------------------


@dataclass(frozen=True)
class CapacityReport:
    passes: int  # distinct pass_id among feasible windows over the horizon
    passes_per_72h: float
    acquisitions: int  # attempted acquisitions actually executed
    acquisitions_per_pass: float | None
    sources: int
    capacity_to_demand_ratio: float | None  # acquisitions / (sources * passes)


def capacity_report(run: RunRecord, horizon_hours: float) -> CapacityReport:
    """Demand is "every source on every pass"; capacity is what the run actually acquired.

    A ratio near 1 means almost everything gets looked at whatever the policy, so policies can
    differ only in order and the benchmark has little room to discriminate.
    """
    passes = len({w.pass_id for w in run.windows if w.feasible})
    acquisitions = sum(a.outcome.value != "NOT_OBSERVED" for a in run.acquisitions)
    sources = len(run.sources)
    return CapacityReport(
        passes=passes,
        passes_per_72h=passes * 72.0 / horizon_hours,
        acquisitions=acquisitions,
        acquisitions_per_pass=acquisitions / passes if passes else None,
        sources=sources,
        capacity_to_demand_ratio=acquisitions / (sources * passes) if passes and sources else None,
    )


@dataclass(frozen=True)
class GateReport:
    gate: GateResult
    capacity: tuple[CapacityReport, ...]  # one per tuning seed (from the random reference runs)
    family: str

    def verdict_text(self) -> str:
        g = self.gate
        word = "PASS" if g.passed else "FAIL"
        return (
            f"G4.5 {word} on {self.family}: oracle-minus-random Brier gap {g.gap:.4f} vs "
            f"2 x SD {2 * g.sd_paired:.4f} over {g.n_seeds} tuning seeds"
        )


def gate_report(
    family: str,
    oracle_brier: Sequence[float],
    random_brier: Sequence[float],
    random_runs: Sequence[RunRecord],
    horizon_hours: float,
) -> GateReport:
    return GateReport(
        gate=discriminability_gate(oracle_brier, random_brier),
        capacity=tuple(capacity_report(r, horizon_hours) for r in random_runs),
        family=family,
    )
