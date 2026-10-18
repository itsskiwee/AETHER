"""Planner policies: five competitors and the seeded random reference policy."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Protocol

from aether.contracts.enums import PolicyId
from aether.contracts.models import CandidateUtility, Plan
from aether.planning.context import PlanningContext
from aether.planning.cpsat import solve_schedule
from aether.planning.greedy import build_heuristic_plan, greedy_insert, rejection_reasons
from aether.rng import keyed_rng


class Policy(Protocol):
    policy_id: PolicyId

    def plan(self, ctx: PlanningContext) -> Plan: ...


class _GreedyPolicy:
    policy_id: PolicyId

    def __init__(self) -> None:
        self.last_rejection_reasons: dict[str, str] = {}

    def _greedy(self, ctx: PlanningContext, order: list[str]) -> Plan:
        selected, _ = greedy_insert(
            ctx.windows,
            order,
            ctx.utilities,
            ctx.cfg.spacecraft,
            ctx.cfg.planner,
            ctx.committed,
            ctx.committed_selections,
            now_utc=ctx.now_utc,
        )
        self.last_rejection_reasons = rejection_reasons(
            ctx.windows,
            selected,
            ctx.utilities,
            ctx.cfg.planner,
            ctx.cfg.spacecraft,
            ctx.committed,
            ctx.committed_selections,
            now_utc=ctx.now_utc,
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


class FirstFeasible(_GreedyPolicy):
    policy_id = PolicyId.FIRST_FEASIBLE

    def plan(self, ctx: PlanningContext) -> Plan:
        rate = ctx.cfg.evaluation.first_feasible_request_rate_per_source_per_day
        horizon_days = ctx.cfg.planner.lookahead_hours / 24.0
        first_request = {}
        sources = sorted({window.source_id for window in ctx.windows})
        for source_id in sources:
            rng = keyed_rng(ctx.cfg.random_seed, "requests", source_id)
            count = int(rng.poisson(rate * horizon_days))
            arrivals = sorted(float(value) for value in rng.uniform(0.0, horizon_days, count))
            if arrivals:
                first_request[source_id] = ctx.now_utc + timedelta(days=arrivals[0])
        source_order = sorted(sources, key=lambda s: (first_request.get(s, ctx.now_utc), s))
        by_source: dict[str, list] = defaultdict(list)
        for window in ctx.windows:
            if window.source_id in first_request:
                request_time = first_request[window.source_id]
                if any(option.start_utc >= request_time for option in window.options):
                    by_source[window.source_id].append(window)
        ordered_ids = [
            window.id
            for source_id in source_order
            for window in sorted(
                by_source[source_id],
                key=lambda w: (
                    min(o.start_utc for o in w.options if o.start_utc >= first_request[source_id]),
                    w.id,
                ),
            )
        ]
        return self._greedy(ctx, ordered_ids)


class LargestFirst(_GreedyPolicy):
    policy_id = PolicyId.LARGEST_FIRST

    def plan(self, ctx: PlanningContext) -> Plan:
        prior_median = ctx.cfg.sources.flux_prior.median_kg_h
        order = sorted(
            (w.id for w in ctx.windows),
            key=lambda wid: (
                -ctx.posterior_mean_flux_kg_h.get(
                    next(w.source_id for w in ctx.windows if w.id == wid), prior_median
                ),
                wid,
            ),
        )
        return self._greedy(ctx, order)


class StaticPriority:
    """CP-SAT policy that freezes each source's initial maximum EIG priority."""

    policy_id = PolicyId.STATIC_PRIORITY

    def __init__(self) -> None:
        self._priority_by_source: dict[str, tuple[float, int]] = {}
        self.last_rejection_reasons: dict[str, str] = {}

    def plan(self, ctx: PlanningContext) -> Plan:
        if ctx.revision == 0:
            initial: dict[str, list[CandidateUtility]] = defaultdict(list)
            for window in sorted(ctx.windows, key=lambda item: item.id):
                if window.id in ctx.utilities:
                    initial[window.source_id].append(ctx.utilities[window.id])
            self._priority_by_source = {
                source_id: max(
                    ((u.expected_info_gain_bits, u.integer_utility) for u in source_utilities),
                )
                for source_id, source_utilities in sorted(initial.items())
            }
        static_utilities = {}
        source_for_window = {window.id: window.source_id for window in ctx.windows}
        for window_id, utility in ctx.utilities.items():
            priority = self._priority_by_source.get(source_for_window.get(window_id, ""))
            if priority is None:
                continue
            static_utilities[window_id] = CandidateUtility(
                window_id=utility.window_id,
                plan_revision=utility.plan_revision,
                expected_info_gain_bits=priority[0],
                decision_relevance=utility.decision_relevance,
                latency_s=utility.latency_s,
                resource_cost=utility.resource_cost,
                p_valid_forecast=utility.p_valid_forecast,
                utility=priority[0],
                integer_utility=priority[1],
            )
        plan, _ = _cp_plan(ctx, self.policy_id, static_utilities)
        self.last_rejection_reasons = rejection_reasons(
            ctx.windows,
            plan.selections,
            static_utilities,
            ctx.cfg.planner,
            ctx.cfg.spacecraft,
            ctx.committed,
            ctx.committed_selections,
            now_utc=ctx.now_utc,
        )
        return plan


class AdaptiveEig:
    policy_id = PolicyId.ADAPTIVE_EIG

    def __init__(self) -> None:
        self.last_rejection_reasons: dict[str, str] = {}

    def plan(self, ctx: PlanningContext) -> Plan:
        plan, _ = _cp_plan(ctx, self.policy_id, ctx.utilities)
        self.last_rejection_reasons = rejection_reasons(
            ctx.windows,
            plan.selections,
            ctx.utilities,
            ctx.cfg.planner,
            ctx.cfg.spacecraft,
            ctx.committed,
            ctx.committed_selections,
            now_utc=ctx.now_utc,
        )
        return plan


class GreedyEig(_GreedyPolicy):
    policy_id = PolicyId.GREEDY_EIG

    def plan(self, ctx: PlanningContext) -> Plan:
        order = sorted(
            (w.id for w in ctx.windows),
            key=lambda wid: (
                -ctx.utilities[wid].expected_info_gain_bits if wid in ctx.utilities else 0.0,
                wid,
            ),
        )
        return self._greedy(ctx, order)


class RandomFeasible(_GreedyPolicy):
    policy_id = PolicyId.RANDOM_FEASIBLE

    def plan(self, ctx: PlanningContext) -> Plan:
        rng = keyed_rng(ctx.cfg.random_seed, "reference", self.policy_id.value)
        order = sorted(w.id for w in ctx.windows)
        if order:
            order = [order[index] for index in rng.permutation(len(order))]
        return self._greedy(ctx, order)


def _cp_plan(ctx: PlanningContext, policy_id: PolicyId, utilities: dict[str, CandidateUtility]):
    return solve_schedule(
        ctx.windows,
        utilities,
        ctx.cfg.spacecraft,
        ctx.cfg.planner,
        ctx.committed,
        committed_selections=ctx.committed_selections,
        run_id=ctx.run_id,
        revision=ctx.revision,
        created_at_sim_utc=ctx.now_utc,
        cause=ctx.cause,
        policy_id=policy_id,
        random_seed=ctx.cfg.random_seed,
    )


__all__ = [
    "AdaptiveEig",
    "FirstFeasible",
    "GreedyEig",
    "LargestFirst",
    "Policy",
    "RandomFeasible",
    "StaticPriority",
]
