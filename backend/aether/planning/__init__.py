"""Lanes L5 (solver and policies) and L8 (independent checker).

Interface (tasks PLN-01..PLN-06, CHK-01..CHK-03):

    planning/cpsat.py   (L5)
        solve_schedule(windows, utilities: dict[window_id, CandidateUtility],
                       spacecraft: dict[str, SpacecraftProfile], planner_cfg,
                       committed: list[ObservationWindow]) -> tuple[Plan, dict[str, datetime]]
            One Boolean per AcquisitionOption; at most one option per window. Plans store explicit
            Selection(window_id, option_id) records; options remain intact on each window.
            Because options have fixed times, slew is exact: for every same-spacecraft option pair
            (i before j) with
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
        check_schedule(plan, windows, sources, spacecraft_profiles, sensor_profile, scenario)
            -> CheckReport
        Resolves each Selection.option_id only within its named window. Re-derives feasibility
        from raw configuration and model-view source coordinates. Uses independent SGP4 and
        Astropy TEME/ITRS and solar geometry with the shared pinned IERS table; never imports
        aether.orbit or consumes its geometry. Recomputes LOS at each option's start/end and
        calculates slew independently.
"""
