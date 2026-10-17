"""Per-source belief filter: a 3-regime mixture HMM with a static ln-flux grid (SCI-03..SCI-05).

State tensor ``P[r, z, g]`` over regime r (static per source), activity z in {0, 1} for the current
1 h bin, and the source's on-rate Q on grid point g. Q is static per source; truth varies it hourly
as ``q = Q * exp(eps)``, ``eps ~ N(0, sigma_h)`` (PR-P11).

Likelihoods are exact marginals over the two nuisance terms the belief does not track:

- hourly variability ``eps`` (PR-P11), which moves both POD and the measured flux;
- error in the wind estimate the belief sees (PR-W13): ``ln U_true ~ N(ln U_est, sigma_w)``
  (flat-prior inversion of the analysis error), which moves POD only.

For a detection with measured flux m and ``a = ln m - ln Q``, the eps integral factorizes as
``N(a; 0, sigma_eff) * E[pod | eps ~ N(mu*, s*)]`` with ``sigma_eff = sqrt(sigma_m^2 + sigma_h^2)``
(PR-V41), ``mu* = a sigma_h^2 / sigma_eff^2`` and ``s* = sigma_h sigma_m / sigma_eff``. The
remaining expectation uses Gauss-Hermite quadrature (PR-B03). With constant POD this reduces
exactly to the sigma_eff measurement density in the interface docstring.

Pure model-view code. Must never import aether.simulation or aether.evaluation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
from numpy.polynomial.hermite_e import hermegauss
from numpy.typing import NDArray
from scipy.special import ndtr

from aether.config import ScenarioConfig, SensorProfile
from aether.contracts.enums import ObservationOutcome, Regime
from aether.contracts.models import BeliefSnapshot, SimulatedAcquisition
from aether.sensors import false_positive_flux_logpdf, pod

MODEL_VERSION = "belief-hmm3-lngrid-v1"
QUADRATURE_NODES = 16  # PR-B03 Gauss-Hermite nodes per nuisance dimension
_HOUR = timedelta(hours=1)
_LN_SQRT_2PI = 0.5 * math.log(2.0 * math.pi)


def binary_entropy_bits(p: float) -> float:
    """H(p) in bits with H(0) = H(1) = 0."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return float(-p * math.log2(p) - (1.0 - p) * math.log2(1.0 - p))


def _gauss_hermite(n: int) -> tuple[NDArray, NDArray]:
    """Nodes and weights for E[f(X)], X ~ N(0, 1)."""
    x, w = hermegauss(n)
    return x, w / w.sum()


@dataclass(frozen=True, eq=False)
class BeliefModel:
    """Everything the filter derives from the model-view config. Shared by all sources."""

    epoch_utc: datetime
    regimes: tuple[Regime, ...]
    regime_weights: NDArray  # (R,)
    transitions: NDArray  # (R, 2, 2), T[r, z_from, z_to] for one 1 h step
    stationary_p_active: NDArray  # (R,)
    ln_q: NDArray  # (G,) grid point ln-flux, kg/h
    ln_edges: NDArray  # (G + 1,) bin edges in ln-flux
    flux_prior: NDArray  # (G,) prior mass of Q per bin, sums to 1
    sigma_hourly_ln: float
    wind_sigma_ln: float
    nodes: NDArray
    weights: NDArray

    @classmethod
    def from_config(cls, cfg: ScenarioConfig) -> BeliefModel:
        regimes = tuple(r.name for r in cfg.sources.regimes)
        weights = np.array([r.weight for r in cfg.sources.regimes], dtype=float)
        trans = np.empty((len(regimes), 2, 2))
        for i, r in enumerate(cfg.sources.regimes):
            a, b = r.p_on_to_off, r.p_off_to_on
            trans[i] = [[1.0 - b, b], [a, 1.0 - a]]
        stationary = np.array([r.stationary_p_active for r in cfg.sources.regimes])

        grid = cfg.planner.belief_grid
        if grid.flux_max_kg_h <= grid.flux_min_kg_h:
            raise ValueError("belief_grid.flux_max_kg_h must exceed flux_min_kg_h")
        ln_q = np.linspace(
            math.log(grid.flux_min_kg_h), math.log(grid.flux_max_kg_h), grid.flux_points
        )
        half = 0.5 * (ln_q[1] - ln_q[0])
        ln_edges = np.concatenate([ln_q - half, [ln_q[-1] + half]])

        # Truncated lognormal prior (PR-P10), integrated exactly over each ln-flux bin.
        prior = cfg.sources.flux_prior
        lo, hi = math.log(prior.min_kg_h), math.log(prior.max_kg_h)
        if hi <= ln_edges[0] or lo >= ln_edges[-1]:
            raise ValueError("flux prior support does not overlap the belief grid")
        z = (np.clip(ln_edges, lo, hi) - math.log(prior.median_kg_h)) / prior.sigma_ln
        mass = np.diff(ndtr(z))
        flux_prior = mass / mass.sum()

        nodes, quad_w = _gauss_hermite(QUADRATURE_NODES)
        for arr in (weights, trans, stationary, ln_q, ln_edges, flux_prior, nodes, quad_w):
            arr.setflags(write=False)
        return cls(
            epoch_utc=cfg.simulation_epoch_utc,
            regimes=regimes,
            regime_weights=weights,
            transitions=trans,
            stationary_p_active=stationary,
            ln_q=ln_q,
            ln_edges=ln_edges,
            flux_prior=flux_prior,
            sigma_hourly_ln=cfg.sources.hourly_variability_sigma_ln,
            wind_sigma_ln=cfg.weather.wind.analysis_error_sigma_ln,
            nodes=nodes,
            weights=quad_w,
        )

    # --- time ---------------------------------------------------------------------------------

    def hour_bin(self, t_utc: datetime) -> int:
        """Index of the 1 h state bin containing t, matching the truth convention."""
        if t_utc < self.epoch_utc:
            raise ValueError(f"{t_utc} is before the simulation epoch {self.epoch_utc}")
        return int((t_utc - self.epoch_utc) // _HOUR)

    def step_matrices(self, steps: int) -> NDArray:
        """(R, 2, 2) transition matrices for ``steps`` hours."""
        if steps < 0:
            raise ValueError("cannot predict backwards in time")
        return np.stack([np.linalg.matrix_power(t, steps) for t in self.transitions])

    # --- likelihood pieces --------------------------------------------------------------------

    def _wind_samples(self, wind_estimate_m_s: float) -> NDArray:
        if wind_estimate_m_s <= 0:
            raise ValueError("wind estimate must be positive")
        if self.wind_sigma_ln == 0.0:
            return np.array([wind_estimate_m_s])
        return wind_estimate_m_s * np.exp(self.wind_sigma_ln * self.nodes)

    def _wind_weights(self) -> NDArray:
        return np.array([1.0]) if self.wind_sigma_ln == 0.0 else self.weights

    def _expected_pod(
        self, sensor: SensorProfile, ln_q: NDArray, wind_m_s: float, off_nadir_deg: float
    ) -> NDArray:
        """E over wind error of POD at the given ln-flux values; ln_q has shape (..., I)."""
        winds = self._wind_samples(wind_m_s)
        p = pod(sensor, np.exp(ln_q)[..., None], winds, off_nadir_deg)  # (..., I, J)
        return p @ self._wind_weights()

    def pod_active(self, sensor: SensorProfile, wind_m_s: float, off_nadir_deg: float) -> NDArray:
        """(G,) P(detection | valid, active, Q_g), marginal over hourly variability and wind."""
        if self.sigma_hourly_ln == 0.0:
            return self._expected_pod(sensor, self.ln_q[:, None], wind_m_s, off_nadir_deg)[:, 0]
        ln_q = self.ln_q[:, None] + self.sigma_hourly_ln * self.nodes[None, :]
        return self._expected_pod(sensor, ln_q, wind_m_s, off_nadir_deg) @ self.weights

    def log_detection_density(
        self,
        sensor: SensorProfile,
        measured_flux_kg_h: float,
        wind_m_s: float,
        off_nadir_deg: float,
    ) -> NDArray:
        """(2, G) log of P(detect, ln m | z, Q_g, valid), a density per unit ln-flux."""
        if not measured_flux_kg_h > 0:
            raise ValueError("a detection needs a positive measured flux")
        ln_m = math.log(measured_flux_kg_h)
        s_m, s_h = sensor.flux_measurement.sigma_ln, self.sigma_hourly_ln
        s_eff = math.sqrt(s_m * s_m + s_h * s_h)
        a = ln_m - self.ln_q  # (G,)
        log_meas = -0.5 * (a / s_eff) ** 2 - math.log(s_eff) - _LN_SQRT_2PI
        if s_h == 0.0:
            p_det = self._expected_pod(sensor, self.ln_q[:, None], wind_m_s, off_nadir_deg)[:, 0]
        else:
            mu = a * (s_h * s_h) / (s_eff * s_eff)
            s_star = s_h * s_m / s_eff
            ln_q = self.ln_q[:, None] + mu[:, None] + s_star * self.nodes[None, :]
            p_det = self._expected_pod(sensor, ln_q, wind_m_s, off_nadir_deg) @ self.weights
        with np.errstate(divide="ignore"):
            log_active = np.log(p_det) + log_meas
        fp = sensor.false_positive_prob
        log_inactive = (math.log(fp) if fp > 0 else -math.inf) + false_positive_flux_logpdf(
            sensor, ln_m
        )
        return np.stack([np.full_like(log_active, log_inactive), log_active])

    def flux_quantile(self, mass: NDArray, q: float) -> float:
        """Quantile of Q from bin masses, with a CDF linear in ln-flux inside each bin."""
        cdf = np.concatenate([[0.0], np.cumsum(mass)])
        cdf /= cdf[-1]
        k = int(np.searchsorted(cdf, q, side="left"))
        k = min(max(k, 1), len(mass))
        while mass[k - 1] <= 0.0 and k < len(mass):  # skip empty bins
            k += 1
        lo_c, hi_c = cdf[k - 1], cdf[k]
        frac = 0.0 if hi_c <= lo_c else (q - lo_c) / (hi_c - lo_c)
        frac = min(max(frac, 0.0), 1.0)
        return float(
            math.exp(self.ln_edges[k - 1] + frac * (self.ln_edges[k] - self.ln_edges[k - 1]))
        )


_MODEL_CACHE: dict[int, tuple[ScenarioConfig, BeliefModel]] = {}


def belief_model(cfg: ScenarioConfig) -> BeliefModel:
    """Cached BeliefModel for a config object (identity-keyed; configs are frozen)."""
    hit = _MODEL_CACHE.get(id(cfg))
    if hit is not None and hit[0] is cfg:
        return hit[1]
    model = BeliefModel.from_config(cfg)
    _MODEL_CACHE[id(cfg)] = (cfg, model)
    return model


def _normalized(log_or_lin: NDArray, *, log: bool) -> NDArray:
    if log:
        finite = np.isfinite(log_or_lin)
        if not finite.any():
            raise ValueError("evidence has zero likelihood under every state")
        out = np.exp(log_or_lin - log_or_lin[finite].max())
    else:
        out = np.array(log_or_lin, dtype=float)
    total = out.sum()
    if not total > 0:
        raise ValueError("evidence has zero likelihood under every state")
    out /= total
    out.setflags(write=False)
    return out


@dataclass(frozen=True, eq=False)
class SourceBelief:
    """Immutable belief about one source. Every operation returns a new object."""

    source_id: str
    model: BeliefModel
    state_time_utc: datetime
    tensor: NDArray  # (R, 2, G), sums to 1, read-only
    evidence_ids: tuple[str, ...] = ()
    received_new_evidence: bool = False
    _hour: int = field(default=-1, repr=False)

    def __post_init__(self) -> None:
        if self._hour < 0:
            object.__setattr__(self, "_hour", self.model.hour_bin(self.state_time_utc))

    # --- construction and propagation ---------------------------------------------------------

    @classmethod
    def prior(cls, source_id: str, cfg: ScenarioConfig) -> SourceBelief:
        """Regime weights x per-regime stationary activity x truncated lognormal flux prior."""
        m = belief_model(cfg)
        pz = np.stack([1.0 - m.stationary_p_active, m.stationary_p_active], axis=1)  # (R, 2)
        tensor = m.regime_weights[:, None, None] * pz[:, :, None] * m.flux_prior[None, None, :]
        return cls(
            source_id=source_id,
            model=m,
            state_time_utc=m.epoch_utc,
            tensor=_normalized(tensor, log=False),
        )

    def predict(self, to_utc: datetime) -> SourceBelief:
        """Markov step(s) to the hour bin containing ``to_utc``. Adds no evidence."""
        steps = self.model.hour_bin(to_utc) - self._hour
        if steps < 0:
            raise ValueError(f"cannot predict {self.source_id} back from {self.state_time_utc}")
        if steps == 0 and to_utc == self.state_time_utc and not self.received_new_evidence:
            return self
        tensor = self.tensor
        if steps > 0:
            tensor = np.einsum("rab,rag->rbg", self.model.step_matrices(steps), self.tensor)
            tensor = _normalized(tensor, log=False)
        return SourceBelief(
            source_id=self.source_id,
            model=self.model,
            state_time_utc=to_utc,
            tensor=tensor,
            evidence_ids=self.evidence_ids,
            received_new_evidence=False,
            _hour=self._hour + steps,
        )

    def update(self, acq: SimulatedAcquisition, *, sensor: SensorProfile) -> SourceBelief:
        """Assimilate one simulated acquisition (PRD 5.5-5.6).

        INVALID_ACQUISITION and NOT_OBSERVED return ``self`` unchanged (bit-identical tensor): they
        carry no emission evidence. Otherwise the belief is first predicted to the acquisition time.
        The likelihood uses ``acq.wind_estimate_m_s`` (never true wind); the scene-validity factor
        is state-independent and cancels.
        """
        if acq.source_id != self.source_id:
            raise ValueError(f"acquisition for {acq.source_id} applied to {self.source_id}")
        if acq.sensor_id != sensor.id:
            raise ValueError(f"acquisition sensor {acq.sensor_id} != profile {sensor.id}")
        if acq.outcome in (ObservationOutcome.INVALID_ACQUISITION, ObservationOutcome.NOT_OBSERVED):
            return self
        prior = self.predict(acq.time_utc)
        m = self.model
        if acq.outcome is ObservationOutcome.DETECTION:
            if acq.measured_flux_kg_h is None:
                raise ValueError("DETECTION without a measured flux")
            log_lik = m.log_detection_density(
                sensor, acq.measured_flux_kg_h, acq.wind_estimate_m_s, acq.off_nadir_deg
            )
        elif acq.outcome is ObservationOutcome.VALID_NON_DETECTION:
            pod_g = m.pod_active(sensor, acq.wind_estimate_m_s, acq.off_nadir_deg)
            with np.errstate(divide="ignore"):
                log_lik = np.log(
                    np.stack([np.full_like(pod_g, 1.0 - sensor.false_positive_prob), 1.0 - pod_g])
                )
        else:  # pragma: no cover - enum is closed
            raise ValueError(f"unknown outcome {acq.outcome}")
        with np.errstate(divide="ignore"):
            log_post = np.log(prior.tensor) + log_lik[None, :, :]
        return SourceBelief(
            source_id=self.source_id,
            model=m,
            state_time_utc=prior.state_time_utc,
            tensor=_normalized(log_post, log=True),
            evidence_ids=(*self.evidence_ids, acq.id),
            received_new_evidence=True,
            _hour=prior._hour,
        )

    # --- summaries ----------------------------------------------------------------------------

    def p_active(self) -> float:
        return float(min(1.0, max(0.0, self.tensor[:, 1, :].sum())))

    def entropy_bits(self) -> float:
        return binary_entropy_bits(self.p_active())

    def regime_probs(self) -> dict[Regime, float]:
        marg = self.tensor.sum(axis=(1, 2))
        marg = marg / marg.sum()
        return {r: float(p) for r, p in zip(self.model.regimes, marg, strict=True)}

    def flux_mass(self) -> NDArray:
        """(G,) posterior mass of the source's on-rate Q (rate when active)."""
        return self.tensor.sum(axis=(0, 1))

    def flux_median_kg_h(self) -> float:
        return self.model.flux_quantile(self.flux_mass(), 0.5)

    def flux_ci90_kg_h(self) -> tuple[float, float]:
        mass = self.flux_mass()
        return self.model.flux_quantile(mass, 0.05), self.model.flux_quantile(mass, 0.95)

    def posterior_mean_flux_kg_h(self) -> float:
        """E[Q] on the grid; used by largest_first."""
        return float(self.flux_mass() @ np.exp(self.model.ln_q))

    def snapshot(self) -> BeliefSnapshot:
        lo, hi = self.flux_ci90_kg_h()
        median = min(max(self.flux_median_kg_h(), lo), hi)
        return BeliefSnapshot(
            source_id=self.source_id,
            state_time_utc=self.state_time_utc,
            p_active=self.p_active(),
            regime_probs=self.regime_probs(),
            flux_median_kg_h=median,
            flux_ci90_kg_h=(lo, hi),
            entropy_bits=self.entropy_bits(),
            model_version=MODEL_VERSION,
            evidence_ids=self.evidence_ids,
            received_new_evidence=self.received_new_evidence,
        )


__all__ = ["BeliefModel", "SourceBelief", "belief_model", "binary_entropy_bits"]
