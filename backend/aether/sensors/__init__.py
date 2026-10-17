"""Lane L2 (science). Virtual sensor response models. Pure functions, no I/O.

Interface (tasks SCI-01, SCI-02):

    gsd_effective_m(sensor, off_nadir_deg) -> float
        gsd_nadir / cos(theta) ** gsd_off_nadir_exponent
    q50_kg_h(sensor, wind_m_s, off_nadir_deg) -> float
        q50_ref * (clip(U)/U_ref) ** wind_exp * (gsd_eff/gsd_ref) ** gsd_exp
    pod(sensor, q_kg_h, wind_m_s, off_nadir_deg) -> float
        1 / (1 + exp(-k (ln q - ln q50))), k = sensor.pod.logistic_slope; pod(0) == 0
    p_valid(sensor, cloud_fraction, off_nadir_deg, max_off_nadir_deg) -> float
        retrieval_success * (1 - cloud_fraction) * (1 - penalty * (theta/theta_max) ** 2)
    p_detect(sensor, active: bool, q_kg_h, wind_m_s, off_nadir_deg) -> float
        P(DETECTION | valid, state) = pod(q) if active else false_positive_prob.
        ONE definition, used by both the simulator and the belief (no FP term for active sources).
    false_positive_flux_logpdf(sensor, ln_measured) -> float
        log density of the reported ln-flux for a false alarm (lognormal PR-V21). The simulator
        samples FP fluxes from the same distribution, so m0 stays well specified.

Both the simulator (truth view) and the belief filter (model view) call these with their own
SensorProfile, which is how the m2/m4 misspecification families take effect.
"""
