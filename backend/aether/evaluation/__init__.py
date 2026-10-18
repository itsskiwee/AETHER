"""Lane L3 (evaluation). The only consumer of truth besides the simulator.

Interface (tasks EVL-01..EVL-08; definitions and decisions in docs/validation-report.md):

    metrics.score_run(run, truth, cfg_model) -> dict[str, float | int | None]
        brier_active_state, log_loss_active_state, ece_active_state (PR-E09),
        flux_interval_coverage_90, each with [regime=R] and [observed=yes|no] breakdowns and
        n_points / n_sources denominators; time_to_corroboration_hours (restricted mean,
        right-censored) + corroborated/censored counts; high_impact_recall_at_5 (None and counted
        when a seed has no high-impact source); acquisition, solver and checker accounting.
        Requires a BeliefSnapshot for every source at every evaluation time (raises otherwise).
    stats.paired_bootstrap(a, b, resamples, level, seed, comparison_id) -> PairedBootstrap
        mean_diff, lo, hi, p_value, n (rng namespace "bootstrap")
    stats.holm, stats.success_verdict, stats.discriminability_gate, stats.seeds_for_power
    protocol.load_protocol, protocol.read_seeds, protocol.check_seed_access
        holdout seeds refused unless locked: true AND committed AND tagged (EVL-05)
    reference.OraclePolicy(truth)   reads truth; built only by the simulation runner (EVL-08)
    reference.capacity_report, reference.gate_report   (G4.5)
    benchmark.benchmark(protocol_path, seeds_path, out_dir, run_fn=default_run_fn) -> dict
        writes benchmark-runs.csv, benchmark-results.csv, benchmark-confidence-intervals.json
    development.development_comparison(repo, out_dir, seeds=(1000,)) -> dict
        base.yaml only, approved development seeds, preliminary evaluator artifacts and measured
        complete-run wall time in a separate nondeterministic sidecar; never a holdout verdict
"""
