"""Lanes L6 (truth, outcomes, weather) and L1 (runner). The ONLY package that reads bundle.truth.

Interface (tasks SIM-03..SIM-06, INT-03):

    simulation/truth.py  (L6, RESTRICTED)
        generate_truth(cfg_truth, sources) -> TruthHistory
            per source: regime, median flux Q_i, hourly z[t] and q[t] = Q_i * exp(eps_t) over the
            horizon. Randomness: aether.rng namespace "truth", key (source_id,).
    simulation/outcomes.py (L6)
        sample_outcome(window, start_utc, truth, weather, sensor_truth, seed)
            -> SimulatedAcquisition
            draws (u_valid, u_det, z_flux, u_fp_flux) from
            keyed_rng(seed, "outcome", source, spacecraft, sensor, minute)
            valid if u_valid < p_valid(cloud_truth, ...); detect if u_det < p_detect(z, q);
            measured = q[t] * exp(sigma_meas * z_flux) if active, else drawn from f_FP.
            wind_estimate = wind_truth * exp(analysis_error_sigma_ln * N(0,1)) (rng "weather",
            "wind_analysis", ...). The returned SimulatedAcquisition carries NO true wind.
    simulation/runner.py (L1)
        run_policy(bundle, policy_id, seed) -> RunRecord
            event-driven loop over passes: predict beliefs -> utilities -> plan -> checker ->
            execute first pass -> update -> replan. Emits RunEvent log; never exposes truth to
            policies. Policies receive a ForecastView of weather (forecast methods only) and
            bundle.model only. Every hand-off re-validates contracts (model_validate) so
            model_construct/model_copy shortcuts cannot smuggle a wrong provenance class.
"""
