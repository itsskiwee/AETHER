"""Lane L3 (evaluation). The only consumer of truth besides the simulator.

Interface (tasks EVL-01..EVL-06):

    score_run(run: RunRecord, truth: TruthHistory, cfg) -> dict[str, float]
        brier_active_state, log_loss_active_state, ece_active_state (10 bins),
        high_impact_recall_at_5 (excluded + counted when a seed has no high-impact source),
        time_to_corroboration_hours (right-censored), per-regime and observed-at-least-once
        breakdowns,
        flux_interval_coverage_90, valid_acquisition_fraction, acquisitions_count
    paired_bootstrap(scores_a, scores_b, resamples, level, seed) -> (mean_diff, lo, hi)
    reference.OraclePolicy / discriminability_gate(...)   (G4.5, EVL-08)
    benchmark(protocol_path, seeds_path) -> writes benchmark-results.csv + CI json
"""
