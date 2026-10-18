"""Scenario configuration: typed schema, loading, family overrides and hashing.

Owned by the integrator lane (L1). ``load_scenario`` returns two views of one scenario:

- ``model``: what the planner and belief filter assume.
- ``truth``: what the hidden simulator uses. Only ``aether.simulation`` and ``aether.evaluation``
  may read it.

They are identical unless a family override is prefixed ``truth:``. Misspecification families
(configs/scenarios/m*.yaml) rely on this.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from aether.contracts.enums import PolicyId, Regime
from aether.contracts.models import FrozenDict, UtcDatetime


class Cfg(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="after")
    def _freeze_nested_mappings(self):
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, dict) and not isinstance(value, FrozenDict):
                object.__setattr__(self, name, FrozenDict(value))
        return self


# --- Region and sources ----------------------------------------------------------------------


class RegionConfig(Cfg):
    region_id: str
    name: str
    bbox_wgs84: tuple[float, float, float, float]
    timezone_note: str = ""
    rationale: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _bbox(self) -> RegionConfig:
        lon0, lat0, lon1, lat1 = self.bbox_wgs84
        if not (-180 <= lon0 < lon1 <= 180 and -90 <= lat0 < lat1 <= 90):
            raise ValueError("bbox must be [lon_min, lat_min, lon_max, lat_max] with min < max")
        return self


class FluxPriorConfig(Cfg):
    family: Literal["lognormal"]
    median_kg_h: float = Field(gt=0)
    sigma_ln: float = Field(gt=0)
    min_kg_h: float = Field(gt=0)
    max_kg_h: float = Field(gt=0)


class RegimeConfig(Cfg):
    name: Regime
    weight: float = Field(ge=0, le=1)
    mean_on_hours: float = Field(gt=1)
    mean_off_hours: float = Field(gt=1)

    @model_validator(mode="after")
    def _chain(self) -> RegimeConfig:
        if 1.0 / self.mean_on_hours + 1.0 / self.mean_off_hours >= 1.0:
            raise ValueError("1/mean_on + 1/mean_off must be < 1 for a 1 h Markov step")
        return self

    @property
    def p_on_to_off(self) -> float:
        """Hourly probability an active source switches off."""
        return 1.0 / self.mean_on_hours

    @property
    def p_off_to_on(self) -> float:
        """Hourly probability an inactive source switches on."""
        return 1.0 / self.mean_off_hours

    @property
    def stationary_p_active(self) -> float:
        return self.p_off_to_on / (self.p_off_to_on + self.p_on_to_off)

    @property
    def correlation_time_hours(self) -> float:
        """e-folding time of the state autocorrelation: -1 / ln(1 - a - b)."""
        lam = 1.0 - self.p_on_to_off - self.p_off_to_on
        return -1.0 / math.log(lam)


class PlumeDatasetConfig(Cfg):
    """A pinned real-plume dataset (docs/dataset-interface.md). Locations only, never truth.

    ``manifest`` is relative to the repository root. ``manifest_sha256`` is part of the config
    hash, so a locked protocol binds the exact dataset bytes.
    """

    manifest: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _relative(self) -> PlumeDatasetConfig:
        path = PurePosixPath(self.manifest)
        if "\\" in self.manifest or path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("plume_dataset.manifest must be a repo-relative POSIX path")
        return self


class SourcesConfig(Cfg):
    count: int = Field(ge=1, le=500)
    placement: Literal["emit_fixture_then_uniform", "uniform"]
    min_separation_m: float = Field(ge=0)
    flux_prior: FluxPriorConfig
    hourly_variability_sigma_ln: float = Field(ge=0)
    regimes: tuple[RegimeConfig, ...]
    # None is the documented synthetic-only mode: every source is uniform fill.
    plume_dataset: PlumeDatasetConfig | None = None

    @model_validator(mode="after")
    def _weights(self) -> SourcesConfig:
        if self.plume_dataset is not None and self.placement != "emit_fixture_then_uniform":
            raise ValueError("plume_dataset requires placement 'emit_fixture_then_uniform'")
        total = sum(r.weight for r in self.regimes)
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"regime weights must sum to 1, got {total}")
        if len({r.name for r in self.regimes}) != len(self.regimes):
            raise ValueError("duplicate regime names")
        return self


# --- Sensors and spacecraft ------------------------------------------------------------------


class PodConfig(Cfg):
    family: Literal["logistic_log_flux"]
    q50_ref_kg_h: float = Field(gt=0)
    q90_ref_kg_h: float = Field(gt=0)
    ref_wind_m_s: float = Field(gt=0)
    ref_gsd_m: float = Field(gt=0)
    wind_scaling_exponent: float
    gsd_scaling_exponent: float
    wind_clip_m_s: tuple[float, float]

    @model_validator(mode="after")
    def _order(self) -> PodConfig:
        if self.q90_ref_kg_h <= self.q50_ref_kg_h:
            raise ValueError("q90_ref_kg_h must exceed q50_ref_kg_h")
        return self

    @property
    def logistic_slope(self) -> float:
        """k in POD = 1 / (1 + exp(-k (ln Q - ln Q50)))."""
        return math.log(9.0) / math.log(self.q90_ref_kg_h / self.q50_ref_kg_h)


class FalsePositiveFluxConfig(Cfg):
    """Density of the reported flux when an inactive source false-alarms (PR-V21).

    Needed so P(detect, measured flux | inactive) is a density like the active case.
    """

    family: Literal["lognormal"]
    median_kg_h: float = Field(gt=0)
    sigma_ln: float = Field(gt=0)


class ValidityConfig(Cfg):
    retrieval_success_prob: float = Field(ge=0, le=1)
    off_nadir_quality_penalty: float = Field(ge=0, le=1)


class FluxMeasurementConfig(Cfg):
    error_family: Literal["lognormal"]
    sigma_ln: float = Field(gt=0)


class SensorCostsConfig(Cfg):
    data_bytes_per_scene: int = Field(gt=0)
    energy_wh_per_scene: float = Field(ge=0)


class SensorProfile(Cfg):
    id: str
    calibration_status: Literal["SIMULATED_PROFILE", "CALIBRATED"]
    gsd_nadir_m: float = Field(gt=0)
    gsd_off_nadir_exponent: float = Field(ge=0)
    scene_size_km: tuple[float, float]
    exposure_seconds: float = Field(gt=0)
    min_sun_elevation_deg: float
    pod: PodConfig
    false_positive_prob: float = Field(ge=0, le=1)
    false_positive_flux: FalsePositiveFluxConfig
    validity: ValidityConfig
    flux_measurement: FluxMeasurementConfig
    costs: SensorCostsConfig


class OrbitConfig(Cfg):
    kind: Literal["keplerian_sgp4init", "gp_omm_json"]
    epoch_utc: UtcDatetime
    plane: int
    altitude_km: float = Field(gt=150)
    inclination_deg: float = Field(ge=0, le=180)
    eccentricity: float = Field(ge=0, lt=1)
    arg_perigee_deg: float
    ltdn: str
    raan_deg: float
    mean_anomaly_deg: float
    bstar: float


class AttitudeConfig(Cfg):
    max_off_nadir_deg: float = Field(gt=0, le=60)
    slew_rate_deg_s: float = Field(gt=0)
    settle_seconds: float = Field(ge=0)


class ResourcesConfig(Cfg):
    battery_capacity_wh: float = Field(gt=0)
    min_state_of_charge: float = Field(ge=0, le=1)
    initial_state_of_charge: float = Field(ge=0, le=1)
    orbit_average_recharge_wh: float = Field(ge=0)
    storage_bytes: int = Field(gt=0)
    max_acquisitions_per_orbit: int = Field(ge=0)


class DownlinkConfig(Cfg):
    model: Literal["fixed_latency_surrogate"]
    latency_seconds: float = Field(ge=0)
    storage_release: Literal["per_orbit"]


class BlackoutConfig(Cfg):
    start_utc: UtcDatetime
    end_utc: UtcDatetime
    reason: str


class SpacecraftProfile(Cfg):
    id: str
    virtual: bool
    profile_version: str
    sensor_ids: tuple[str, ...]
    orbit: OrbitConfig
    attitude: AttitudeConfig
    resources: ResourcesConfig
    downlink: DownlinkConfig
    blackouts: tuple[BlackoutConfig, ...] = ()

    @model_validator(mode="after")
    def _virtual(self) -> SpacecraftProfile:
        if not self.virtual:
            raise ValueError("taskable spacecraft must be virtual=true (PRD 0, boundary 2)")
        return self


# --- Weather, planner, evaluation ------------------------------------------------------------


class CloudConfig(Cfg):
    mean_cloud_fraction: float = Field(ge=0, le=1)
    spatial_corr_length_km: float = Field(gt=0)
    temporal_corr_hours: float = Field(gt=0)
    logit_sigma: float = Field(gt=0)


class ForecastConfig(Cfg):
    logit_error_sigma_base: float = Field(ge=0)
    logit_error_sigma_per_lead_hour: float = Field(ge=0)
    issue_interval_hours: float = Field(gt=0)


class WindConfig(Cfg):
    analysis_error_sigma_ln: float = Field(ge=0)  # PR-W13: wind the belief may use after the fact
    median_m_s: float = Field(gt=0)
    sigma_ln: float = Field(ge=0)
    temporal_corr_hours: float = Field(gt=0)
    min_m_s: float = Field(gt=0)
    max_m_s: float = Field(gt=0)


class InjectedEvent(Cfg):
    kind: Literal["forecast_revision"]
    at_hour: float = Field(ge=0)
    target_source_index: int = Field(ge=0)
    cloud_fraction: float = Field(ge=0, le=1)
    duration_hours: float = Field(gt=0)


class WeatherConfig(Cfg):
    """No seed field: every weather stream derives from the run seed via aether.rng."""

    type: Literal["synthetic_scenario", "era5_replay"]
    cloud: CloudConfig
    forecast: ForecastConfig
    wind: WindConfig
    injected_events: tuple[InjectedEvent, ...] = ()


class SolverConfig(Cfg):
    """Reproducible mode: num_workers=1 plus a deterministic-time limit (CP-SAT
    ``max_deterministic_time``). The solver seed is derived from the run seed (aether.rng)."""

    mode: Literal["reproducible", "fast"]
    max_deterministic_time: float = Field(gt=0)
    num_workers: int = Field(ge=1)
    fast_mode_wall_time_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def _reproducible(self) -> SolverConfig:
        if self.mode == "reproducible" and self.num_workers != 1:
            raise ValueError("reproducible mode requires num_workers=1")
        return self


class BeliefGridConfig(Cfg):
    flux_points: int = Field(ge=8, le=1024)
    flux_min_kg_h: float = Field(gt=0)
    flux_max_kg_h: float = Field(gt=0)
    eig_target: Literal["binary_activity"]


class WindowSearchConfig(Cfg):
    coarse_step_s: float = Field(gt=0)
    refine_tolerance_s: float = Field(gt=0)
    option_step_s: float = Field(gt=0)
    max_options_per_window: int = Field(ge=1)


class PlannerConfig(Cfg):
    lookahead_hours: float = Field(gt=0)
    replan_on: tuple[Literal["pass_completed", "informative_acquisition", "forecast_revision"], ...]
    freeze_current_pass: bool
    max_visits_per_source_per_solve: int = Field(ge=1)
    weights: dict[Literal["information", "decision", "latency", "resource"], float]
    utility_integer_scale: int = Field(ge=1)
    min_utility_bits: float = Field(ge=0)
    utility: Literal["one_step_eig", "brier_reduction_to_next_pass"]
    solver: SolverConfig
    belief_grid: BeliefGridConfig


class EvaluationConfig(Cfg):
    policies: tuple[PolicyId, ...]
    primary_policies_p0: tuple[PolicyId, ...]
    reference_policies: tuple[PolicyId, ...]
    eval_interval_hours: float = Field(gt=0)
    high_impact_mean_rate_kg_h: float = Field(gt=0)
    first_feasible_request_rate_per_source_per_day: float = Field(gt=0)
    corroboration_p_threshold: float = Field(gt=0.5, lt=1)
    bootstrap_resamples: int = Field(ge=100)
    ci_level: float = Field(gt=0, lt=1)
    truth_isolation: Literal["enforced"]


class ScenarioConfig(Cfg):
    schema_version: Literal[1]
    scenario_id: str
    family: str = "m0_well_specified"
    simulation_epoch_utc: UtcDatetime
    horizon_hours: float = Field(gt=0, le=24 * 30)
    random_seed: int = Field(ge=0)
    historical_data_mode: Literal["historical_context_only"]
    orbital_mode: Literal["virtual_taskable_constellation"]
    region: RegionConfig
    spacecraft: dict[str, SpacecraftProfile]
    sensors: dict[str, SensorProfile]
    sources: SourcesConfig
    weather: WeatherConfig
    window_search: WindowSearchConfig
    planner: PlannerConfig
    evaluation: EvaluationConfig

    @model_validator(mode="after")
    def _references(self) -> ScenarioConfig:
        for sc in self.spacecraft.values():
            missing = set(sc.sensor_ids) - set(self.sensors)
            if missing:
                raise ValueError(f"spacecraft {sc.id} references unknown sensors {sorted(missing)}")
        for key, sc in self.spacecraft.items():
            if key != sc.id:
                raise ValueError(f"spacecraft key {key} != id {sc.id}")
        ws = self.window_search
        for sensor in self.sensors.values():
            min_window = sensor.exposure_seconds + min(
                sc.attitude.settle_seconds for sc in self.spacecraft.values()
            )
            if ws.coarse_step_s > min_window / 2:
                raise ValueError(
                    f"window_search.coarse_step_s must be <= half the minimum window "
                    f"({min_window / 2:.1f} s) or short windows are missed"
                )
        for ev in self.weather.injected_events:
            if ev.target_source_index >= self.sources.count:
                raise ValueError("injected event targets a source index beyond sources.count")
        return self

    def config_hash(self) -> str:
        """SHA-256 of the canonical JSON form. Stored on every run, plan and event.

        Canonical form (documented, not RFC 8785): Pydantic ``model_dump(mode="json")`` serialized
        with ``json.dumps(sort_keys=True, separators=(",", ":"))``. Never hash raw YAML text.
        """
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


class ScenarioBundle(Cfg):
    model: ScenarioConfig
    truth: ScenarioConfig  # restricted: simulation and evaluation only

    @model_validator(mode="after")
    def _same_inputs(self) -> ScenarioBundle:
        # Sources are built from the model view; a truth-only dataset would be silently ignored.
        if self.model.sources.plume_dataset != self.truth.sources.plume_dataset:
            raise ValueError("sources.plume_dataset cannot differ between model and truth")
        return self


# --- Loading ---------------------------------------------------------------------------------


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open() as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data


def _deep_merge(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(parent)
    for key, value in child.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _resolve_raw(base_path: Path) -> dict[str, Any]:
    raw = _read_yaml(base_path)
    if "extends" in raw:
        parent = _read_yaml(base_path.parent / raw.pop("extends"))
        if "extends" in parent:
            raise ValueError("only one level of 'extends' is supported")
        raw = _deep_merge(parent, raw)
    root = base_path.parent
    raw["region"] = _read_yaml(root / raw.pop("region_file"))
    spacecraft = [_read_yaml(root / p) for p in raw.pop("spacecraft_files")]
    sensors = [_read_yaml(root / p) for p in raw.pop("sensor_files")]
    raw["spacecraft"] = {s["id"]: s for s in spacecraft}
    raw["sensors"] = {s["id"]: s for s in sensors}
    return raw


def _set_path(node: Any, parts: list[str], value: Any) -> None:
    head, rest = parts[0], parts[1:]
    if head == "*":
        children = node.values() if isinstance(node, dict) else node
        targets = list(children)
        if not targets:
            raise KeyError("wildcard matched nothing")
        for child in targets:
            if rest:
                _set_path(child, rest, value)
            else:
                raise KeyError("wildcard cannot be the final path element")
        return
    key: Any = int(head) if isinstance(node, list) else head
    if isinstance(node, dict) and key not in node:
        raise KeyError(f"override path element {head!r} does not exist")
    if rest:
        _set_path(node[key], rest, value)
    else:
        node[key] = value


def load_scenario(
    base_path: str | Path,
    family_path: str | Path | None = None,
    *,
    seed: int | None = None,
    synthetic_only: bool = False,
) -> ScenarioBundle:
    """Load a base scenario and optionally apply a family override file.

    Override keys are dotted paths into the resolved config (sensors and spacecraft are keyed by
    id; list elements by index; ``*`` matches every child). A ``truth:`` prefix applies the
    override to the hidden-simulator view only. Unknown paths raise ``KeyError``: overrides never
    create new keys silently. ``seed`` replaces ``random_seed``; every random stream (truth,
    weather, outcomes, solver) derives from it, so different seeds give different weather.
    ``synthetic_only`` removes ``sources.plume_dataset`` after overrides (explicit uniform-fill
    mode; the change is visible in the config hash).
    """
    raw = _resolve_raw(Path(base_path))
    if seed is not None:
        raw["random_seed"] = seed
    model_raw = copy.deepcopy(raw)
    truth_raw = copy.deepcopy(raw)
    if family_path is not None:
        family = _read_yaml(Path(family_path))
        model_raw["family"] = truth_raw["family"] = family["family"]
        for dotted, value in (family.get("overrides") or {}).items():
            truth_only = dotted.startswith("truth:")
            parts = dotted.removeprefix("truth:").split(".")
            _set_path(truth_raw, parts, value)
            if not truth_only:
                _set_path(model_raw, parts, value)
    if synthetic_only:
        for view in (model_raw, truth_raw):
            view["sources"]["plume_dataset"] = None
    return ScenarioBundle(
        model=ScenarioConfig.model_validate(model_raw),
        truth=ScenarioConfig.model_validate(truth_raw),
    )
