"""Seeded generation of synthetic source state and emission-rate histories."""

from __future__ import annotations

from datetime import datetime

import numpy as np
from scipy.special import ndtr, ndtri

from aether.config import ScenarioConfig, SourcesConfig
from aether.contracts.enums import Regime
from aether.contracts.models import Source
from aether.rng import keyed_rng
from aether.simulation.truth_types import SourceTruth, TruthHistory


def generate_truth(
    cfg_truth: ScenarioConfig | SourcesConfig,
    sources: list[Source] | tuple[Source, ...],
    *,
    seed: int | None = None,
    epoch_utc: datetime | None = None,
    horizon_hours: float | None = None,
) -> TruthHistory:
    """Generate hidden truth using a distinct keyed stream for each source.

    Passing a ``ScenarioConfig`` is preferred. ``SourcesConfig`` is also accepted for isolated
    scientific use, but then ``epoch_utc`` and ``horizon_hours`` are required.
    """
    if isinstance(cfg_truth, ScenarioConfig):
        source_cfg = cfg_truth.sources
        seed = cfg_truth.random_seed if seed is None else seed
        epoch_utc = cfg_truth.simulation_epoch_utc if epoch_utc is None else epoch_utc
        horizon_hours = cfg_truth.horizon_hours if horizon_hours is None else horizon_hours
    else:
        source_cfg = cfg_truth
    if seed is None or epoch_utc is None or horizon_hours is None:
        raise ValueError("seed, epoch_utc and horizon_hours are required with SourcesConfig")
    if epoch_utc.tzinfo is None or epoch_utc.utcoffset() is None:
        raise ValueError("epoch_utc must be timezone-aware")
    if horizon_hours <= 0:
        raise ValueError("horizon_hours must be positive")

    hours = int(np.ceil(horizon_hours))
    regime_probs = np.array([r.weight for r in source_cfg.regimes], dtype=float)
    regime_configs = {r.name: r for r in source_cfg.regimes}
    result: dict[str, SourceTruth] = {}
    for source in sources:
        rng = keyed_rng(seed, "truth", source.id)
        regime = Regime(rng.choice([r.name for r in source_cfg.regimes], p=regime_probs))
        regime_cfg = regime_configs[regime]
        prior = source_cfg.flux_prior
        mu_ln = np.log(prior.median_kg_h)
        sigma_ln = prior.sigma_ln
        cdf_min = ndtr((np.log(prior.min_kg_h) - mu_ln) / sigma_ln)
        cdf_max = ndtr((np.log(prior.max_kg_h) - mu_ln) / sigma_ln)
        median_flux = float(
            np.exp(mu_ln + sigma_ln * ndtri(cdf_min + rng.random() * (cdf_max - cdf_min)))
        )
        active = np.zeros(hours, dtype=bool)
        flux = np.zeros(hours, dtype=float)
        active[0] = rng.random() < regime_cfg.stationary_p_active
        for hour in range(hours):
            if hour:
                p_switch = regime_cfg.p_on_to_off if active[hour - 1] else regime_cfg.p_off_to_on
                active[hour] = not active[hour - 1] if rng.random() < p_switch else active[hour - 1]
            if active[hour]:
                flux[hour] = median_flux * np.exp(
                    rng.normal(0.0, source_cfg.hourly_variability_sigma_ln)
                )
        active.setflags(write=False)
        flux.setflags(write=False)
        result[source.id] = SourceTruth(
            source_id=source.id,
            regime=regime,
            median_flux_kg_h=median_flux,
            active=active,
            flux_kg_h=flux,
        )
    return TruthHistory(
        epoch_utc=epoch_utc,
        hours=hours,
        sources=result,
    )
