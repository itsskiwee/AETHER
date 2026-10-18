"""Deterministic synthetic cloud, wind and forecast fields for virtual scenarios."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Protocol

import numpy as np
from scipy.optimize import brentq
from scipy.special import expit

from aether.config import ScenarioConfig, WeatherConfig
from aether.contracts.models import Source
from aether.rng import keyed_rng


class WeatherModel(Protocol):
    def cloud_truth(self, source_id: str, t_utc: datetime) -> float: ...

    def wind_truth(self, source_id: str, t_utc: datetime) -> float: ...

    def cloud_forecast(self, source_id: str, t_utc: datetime, issued_at_utc: datetime) -> float: ...

    def wind_forecast(self, source_id: str, t_utc: datetime, issued_at_utc: datetime) -> float: ...

    def latest_issue_time(self, now_utc: datetime) -> datetime: ...


def _utc_hours(delta: timedelta) -> float:
    return delta.total_seconds() / 3600.0


def _logit(p: float) -> float:
    # Keep numerical operations finite at the valid endpoints of the configuration schema.
    eps = np.finfo(float).eps
    p = float(np.clip(p, eps, 1.0 - eps))
    return math.log(p / (1.0 - p))


def _calibrated_cloud_intercept(mean: float, sigma: float) -> float:
    if mean == 0:
        return -math.inf
    if mean == 1:
        return math.inf
    # Gauss-Hermite integration computes E[sigmoid(intercept + sigma * N(0,1))].
    nodes, weights = np.polynomial.hermite.hermgauss(40)
    normals = math.sqrt(2.0) * nodes
    weights = weights / math.sqrt(math.pi)

    def error(intercept: float) -> float:
        return float(np.dot(weights, expit(intercept + sigma * normals)) - mean)

    return float(brentq(error, -40.0 - sigma, 40.0 + sigma))


class SyntheticWeather:
    """Truth-owning weather object. Give policies :meth:`forecast_view`, not this instance."""

    def __init__(
        self,
        cfg_truth: ScenarioConfig | WeatherConfig,
        sources: list[Source] | tuple[Source, ...],
        *,
        model_cfg: ScenarioConfig | WeatherConfig | None = None,
        seed: int | None = None,
        epoch_utc: datetime | None = None,
        horizon_hours: float | None = None,
    ) -> None:
        if isinstance(cfg_truth, ScenarioConfig):
            self.truth_cfg = cfg_truth.weather
            self._family = cfg_truth.family
            self.seed = cfg_truth.random_seed if seed is None else seed
            self.epoch_utc = cfg_truth.simulation_epoch_utc if epoch_utc is None else epoch_utc
            self.horizon_hours = cfg_truth.horizon_hours if horizon_hours is None else horizon_hours
            self.sources = tuple(sources)
            self.truth_events = cfg_truth.weather.injected_events
        else:
            self.truth_cfg = cfg_truth
            self._family = ""
            self.seed = 0 if seed is None else seed
            self.epoch_utc = epoch_utc
            self.horizon_hours = horizon_hours
            self.sources = tuple(sources)
            self.truth_events = cfg_truth.injected_events
        if isinstance(model_cfg, ScenarioConfig):
            self.model_cfg = model_cfg.weather
        else:
            self.model_cfg = model_cfg or self.truth_cfg
        if self.epoch_utc is None or self.horizon_hours is None:
            raise ValueError("epoch_utc and horizon_hours are required with WeatherConfig")
        if self.epoch_utc.tzinfo is None or self.epoch_utc.utcoffset() is None:
            raise ValueError("epoch_utc must be timezone-aware")
        if self.horizon_hours <= 0:
            raise ValueError("horizon_hours must be positive")
        self._source_index = {s.id: i for i, s in enumerate(self.sources)}
        if len(self._source_index) != len(self.sources):
            raise ValueError("source ids must be unique")
        self._hours = max(2, math.ceil(self.horizon_hours) + 1)
        self._spatial_factor = self._make_spatial_factor()
        self._wind_forecast_errors: dict[tuple[str, str], np.ndarray] = {}
        self._cloud = self._make_cloud_field()
        self._wind = self._make_wind_field()

    def _make_spatial_factor(self) -> np.ndarray:
        """Factor the configured exponential spatial correlation kernel (PR-W02)."""
        n_sources = len(self.sources)
        if not n_sources:
            return np.empty((0, 0))
        coords = np.asarray([[s.lon, s.lat] for s in self.sources], dtype=float)
        lat0 = math.radians(float(np.mean(coords[:, 1])))
        xy_km = np.column_stack((coords[:, 0] * 111.32 * math.cos(lat0), coords[:, 1] * 110.57))
        distances = np.linalg.norm(xy_km[:, None, :] - xy_km[None, :, :], axis=2)
        covariance = np.exp(-distances / self.truth_cfg.cloud.spatial_corr_length_km)
        eigenvalues, eigenvectors = np.linalg.eigh(covariance)
        return eigenvectors @ np.diag(np.sqrt(np.maximum(eigenvalues, 0.0)))

    def _make_cloud_field(self) -> np.ndarray:
        cfg = self.truth_cfg.cloud
        n_sources = len(self.sources)
        if not n_sources:
            return np.empty((0, self._hours))
        rng = keyed_rng(self.seed, "weather", "cloud")
        phi = math.exp(-1.0 / cfg.temporal_corr_hours)
        latent = np.empty((n_sources, self._hours), dtype=float)
        latent[:, 0] = self._spatial_factor @ rng.standard_normal(n_sources)
        innovation_scale = math.sqrt(1.0 - phi * phi)
        for h in range(1, self._hours):
            latent[:, h] = phi * latent[:, h - 1] + innovation_scale * (
                self._spatial_factor @ rng.standard_normal(n_sources)
            )
        intercept = _calibrated_cloud_intercept(cfg.mean_cloud_fraction, cfg.logit_sigma)
        return intercept + cfg.logit_sigma * latent

    def _make_wind_field(self) -> np.ndarray:
        cfg = self.truth_cfg.wind
        field = np.empty((len(self.sources), self._hours), dtype=float)
        phi = math.exp(-1.0 / cfg.temporal_corr_hours)
        innovation_scale = math.sqrt(1.0 - phi * phi)
        rng = keyed_rng(self.seed, "weather", "wind")
        latent = np.empty((len(self.sources), self._hours), dtype=float)
        latent[:, 0] = self._spatial_factor @ rng.standard_normal(len(self.sources))
        for h in range(1, self._hours):
            latent[:, h] = phi * latent[:, h - 1] + innovation_scale * (
                self._spatial_factor @ rng.standard_normal(len(self.sources))
            )
        field[:] = np.clip(cfg.median_m_s * np.exp(cfg.sigma_ln * latent), cfg.min_m_s, cfg.max_m_s)
        return field

    def _index_and_fraction(self, t_utc: datetime) -> tuple[int, float]:
        if t_utc.tzinfo is None or t_utc.utcoffset() is None:
            raise ValueError("weather times must be timezone-aware")
        x = _utc_hours(t_utc - self.epoch_utc)
        if x < 0 or x > self.horizon_hours:
            raise IndexError(f"{t_utc} outside weather horizon")
        i = min(int(math.floor(x)), self._hours - 2)
        return i, x - i

    def _at(self, field: np.ndarray, source_id: str, t_utc: datetime) -> float:
        if source_id not in self._source_index:
            raise KeyError(f"unknown source {source_id!r}")
        i, frac = self._index_and_fraction(t_utc)
        row = field[self._source_index[source_id]]
        return float(row[i] * (1.0 - frac) + row[i + 1] * frac)

    def _active_event(self, source_id: str, t_utc: datetime) -> float | None:
        source_idx = self._source_index[source_id]
        elapsed = _utc_hours(t_utc - self.epoch_utc)
        for event in self.truth_events:
            if (
                event.target_source_index == source_idx
                and event.at_hour <= elapsed < event.at_hour + event.duration_hours
            ):
                return event.cloud_fraction
        return None

    def cloud_truth(self, source_id: str, t_utc: datetime) -> float:
        event = self._active_event(source_id, t_utc)
        if event is not None:
            return event
        return float(expit(self._at(self._cloud, source_id, t_utc)))

    def wind_truth(self, source_id: str, t_utc: datetime) -> float:
        return self._at(self._wind, source_id, t_utc)

    def latest_issue_time(self, now_utc: datetime) -> datetime:
        if now_utc.tzinfo is None or now_utc.utcoffset() is None:
            raise ValueError("weather times must be timezone-aware")
        interval_s = self.model_cfg.forecast.issue_interval_hours * 3600.0
        elapsed_s = (now_utc - self.epoch_utc).total_seconds()
        regular = self.epoch_utc + timedelta(
            seconds=math.floor(elapsed_s / interval_s) * interval_s
        )
        injections = (
            self.epoch_utc + timedelta(hours=event.at_hour)
            for event in self.truth_events
            if event.at_hour * 3600.0 <= elapsed_s
        )
        return max([regular, *injections])

    def _check_issue(self, issued_at_utc: datetime) -> None:
        if issued_at_utc.tzinfo is None or issued_at_utc.utcoffset() is None:
            raise ValueError("issued_at_utc must be timezone-aware")
        if issued_at_utc > self.epoch_utc + timedelta(hours=self.horizon_hours):
            raise IndexError("forecast issue is outside weather horizon")

    def cloud_forecast(self, source_id: str, t_utc: datetime, issued_at_utc: datetime) -> float:
        self._check_issue(issued_at_utc)
        event = self._active_event(source_id, t_utc)
        # A scripted revision is new information at injection time, never a forecast of a
        # future intervention. Before that time use the unmodified synthetic cloud field.
        known_event = any(
            item.target_source_index == self._source_index[source_id]
            and self.epoch_utc + timedelta(hours=item.at_hour) <= issued_at_utc
            and item.at_hour
            <= _utc_hours(t_utc - self.epoch_utc)
            < item.at_hour + item.duration_hours
            for item in self.truth_events
        )
        if event is not None and known_event:
            return event
        issue = self.latest_issue_time(issued_at_utc)
        lead_h = max(0.0, _utc_hours(t_utc - issue))
        # Realized forecast error follows the truth view; the planner receives these forecast
        # values but continues to reason from its model view and hence can be misspecified.
        fc = self.truth_cfg.forecast
        sigma = fc.logit_error_sigma_base + fc.logit_error_sigma_per_lead_hour * lead_h
        rng = keyed_rng(
            self.seed,
            "weather",
            "forecast",
            "cloud",
            source_id,
            issue.isoformat(),
            t_utc.isoformat(),
        )
        baseline_cloud = float(expit(self._at(self._cloud, source_id, t_utc)))
        logit = _logit(baseline_cloud) + rng.normal(0.0, sigma)
        return float(expit(logit))

    def wind_forecast(self, source_id: str, t_utc: datetime, issued_at_utc: datetime) -> float:
        self._check_issue(issued_at_utc)
        if source_id not in self._source_index:
            raise KeyError(f"unknown source {source_id!r}")
        issue = self.latest_issue_time(issued_at_utc)
        valid_h_index = int(max(0.0, _utc_hours(t_utc - self.epoch_utc)))
        valid_hour = self.epoch_utc + timedelta(hours=valid_h_index)
        # PR-B04 uses the registered flat PR-W13 uncertainty for planning-time wind forecasts;
        # a separate lead-dependent forecast parameter has not been approved or registered.
        sigma = self.truth_cfg.wind.analysis_error_sigma_ln
        key = (issue.isoformat(), valid_hour.isoformat())
        if key not in self._wind_forecast_errors:
            rng = keyed_rng(self.seed, "wind_forecast", *key)
            self._wind_forecast_errors[key] = self._spatial_factor @ rng.standard_normal(
                len(self.sources)
            )
        epsilon = self._wind_forecast_errors[key][self._source_index[source_id]]
        cfg = self.truth_cfg.wind
        return float(
            np.clip(
                self.wind_truth(source_id, t_utc) * math.exp(sigma * epsilon),
                cfg.min_m_s,
                cfg.max_m_s,
            )
        )

    def wind_analysis_estimate(self, source_id: str, t_utc: datetime) -> float:
        """Return the noisy post-acquisition wind estimate; never expose truth to inference."""
        sigma = self.truth_cfg.wind.analysis_error_sigma_ln
        rng = keyed_rng(
            self.seed,
            "weather",
            "wind_analysis",
            source_id,
            t_utc.replace(minute=0, second=0, microsecond=0).isoformat(),
        )
        return float(
            np.clip(
                self.wind_truth(source_id, t_utc) * np.exp(rng.normal(0.0, sigma)),
                self.model_cfg.wind.min_m_s,
                self.model_cfg.wind.max_m_s,
            )
        )

    def forecast_view(self) -> ForecastView:
        return ForecastView(self)


class ForecastView:
    """Planner-side facade exposing forecasts and no truth accessors."""

    __slots__ = ("__weather",)

    def __init__(self, weather: SyntheticWeather) -> None:
        self.__weather = weather

    def cloud_forecast(self, source_id: str, t_utc: datetime, issued_at_utc: datetime) -> float:
        return self.__weather.cloud_forecast(source_id, t_utc, issued_at_utc)

    def wind_forecast(self, source_id: str, t_utc: datetime, issued_at_utc: datetime) -> float:
        return self.__weather.wind_forecast(source_id, t_utc, issued_at_utc)

    def latest_issue_time(self, now_utc: datetime) -> datetime:
        return self.__weather.latest_issue_time(now_utc)


def build_synthetic_weather(
    cfg_truth: ScenarioConfig,
    sources: list[Source] | tuple[Source, ...],
    *,
    model_cfg: ScenarioConfig,
    seed: int | None = None,
) -> SyntheticWeather:
    """Build synthetic weather; truth and forecast config views may differ by family."""
    if (
        cfg_truth.weather.type != "synthetic_scenario"
        or model_cfg.weather.type != "synthetic_scenario"
    ):
        raise ValueError("build_synthetic_weather requires synthetic_scenario weather configs")
    return SyntheticWeather(cfg_truth, sources, model_cfg=model_cfg, seed=seed)
