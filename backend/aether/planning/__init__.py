"""Lanes L5 (solver and policies) and L8 (independent checker).

Interface (tasks PLN-01..PLN-06, CHK-01..CHK-03):

    planning/cpsat.py   (L5)
        solve_schedule(windows, utilities: dict[window_id, CandidateUtility],
                       spacecraft: dict[str, SpacecraftProfile], planner_cfg,
                       committed: list[ObservationWindow]) -> tuple[Plan, dict[str, datetime]]
            One Boolean per AcquisitionOption; at most one option per window. Because options have
            fixed times, slew is exact: for every same-spacecraft option pair (i before j) with
            start_j < end_i + slew_time_s(i, j), add NOT(x_i AND x_j). Optional intervals +
            AddNoOverlap per spacecraft as a second guard. <= max_visits_per_source_per_solve per
            source; <= max_acquisitions_per_orbit per (sat, orbit_number); storage and energy
            cumulative per orbit. Tie-break: lowest option id. Solver seed from
            aether.rng.derive_seed(seed, "solver", policy_id, revision).

    planning/policies.py (L5)
        class Policy(Protocol):
            policy_id: PolicyId
            def plan(self, ctx: PlanningContext) -> Plan
        FirstFeasible, LargestFirst, StaticPriority, AdaptiveEig, GreedyEig, RandomFeasible
        FirstFeasible serves a seeded Poisson request stream (rng "requests",
        first_feasible_request_rate_per_source_per_day) in arrival order (Parameter_2 ENG-SIM-006).
        ORACLE is NOT here: it reads truth and lives in aether.evaluation.reference.
        Greedy policies share one greedy_insert(windows, order, ...) that calls the same
        constraint helpers, so no baseline can produce an illegal schedule.

    planning/checker.py (L8) -- INDEPENDENT. Must not import planning.cpsat or planning.policies.
        check_schedule(selected_option_ids, windows, spacecraft, cfg, committed)
            -> ScheduleValidation
        Re-derives every rule from scratch with plain Python loops. Recomputes LOS, off-nadir and
        sun elevation at each selected option's own start/end time with its OWN sgp4 propagation
        (not aether.orbit), and its own slew math. Mutation test: a deliberately broken
        orbit.slew_time_s must be caught.
"""
