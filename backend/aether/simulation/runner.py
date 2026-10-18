"""Deterministic, truth-isolated closed-loop simulation (INT-03/04)."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from aether import __version__
from aether.belief import SourceBelief, expected_brier_reduction, expected_info_gain_bits
from aether.config import ScenarioBundle, ScenarioConfig
from aether.contracts.enums import EventType, ObservationOutcome, PolicyId
from aether.contracts.models import (
    BeliefSnapshot,
    CandidateUtility,
    FrozenDict,
    InputDatasetRef,
    ObservationWindow,
    Plan,
    PlumeObservation,
    RunEvent,
    RunRecord,
    ScheduleValidation,
    Selection,
    Source,
    revalidate_contract,
)
from aether.evaluation.metrics import evaluation_times
from aether.ingestion import cluster_to_sources, plumes_in_region
from aether.orbit import generate_windows
from aether.planning.checker import check_schedule
from aether.planning.context import PlanningContext
from aether.planning.policies import (
    AdaptiveEig,
    FirstFeasible,
    GreedyEig,
    LargestFirst,
    RandomFeasible,
    StaticPriority,
)
from aether.rng import keyed_rng
from aether.sensors import p_valid
from aether.simulation.outcomes import sample_outcome
from aether.simulation.truth import generate_truth
from aether.simulation.truth_types import TruthHistory
from aether.weather.synthetic import ForecastView, build_synthetic_weather

_WINDOW_CACHE: dict[tuple, tuple[ObservationWindow, ...]] = {}
_DATASET_CACHE: dict[tuple[str, str], Any] = {}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_configured_dataset(cfg: ScenarioConfig):
    """Load and verify the config's pinned plume dataset, or return None in synthetic-only mode.

    Verification (every listed hash, size and record) belongs to ``aether.ingestion``; a missing
    or altered dataset raises rather than falling back to uniform placement. Cached per process
    by manifest path and expected hash, so policies in one process share the same records.
    """
    spec = cfg.sources.plume_dataset
    if spec is None:
        return None
    key = (spec.manifest, spec.manifest_sha256)
    if key not in _DATASET_CACHE:
        from aether.ingestion import load_pinned_plume_dataset

        root = repo_root()
        _DATASET_CACHE[key] = load_pinned_plume_dataset(
            root / spec.manifest,
            expected_manifest_sha256=spec.manifest_sha256,
            repo_root=root,
        )
    return _DATASET_CACHE[key]


def resolve_sources(
    cfg: ScenarioConfig,
    seed: int,
    plume_observations: Iterable[PlumeObservation] | None = None,
) -> tuple[tuple[Source, ...], InputDatasetRef | None]:
    """Build the run's sources from exactly one plume input: the configured dataset or the caller.

    Policy-independent: the result depends only on the model config, the plumes and the seed.
    Caller-supplied plumes are an unpinned input (tests and diagnostics); they are refused when
    the config already names a dataset, so a run never mixes two inputs.
    """
    dataset = load_configured_dataset(cfg)
    if dataset is None:
        return generate_sources(cfg, seed, plume_observations or ()), None
    if plume_observations is not None:
        raise ValueError(
            "the config names a pinned plume dataset; do not also pass plume_observations"
        )
    sources = generate_sources(cfg, seed, dataset.plumes)
    seeded = sum(source.seeded_from_plume_id is not None for source in sources)
    ref = InputDatasetRef(
        dataset_id=dataset.dataset_id,
        manifest_path=cfg.sources.plume_dataset.manifest,
        manifest_sha256=dataset.manifest_sha256,
        normalized_sha256=dataset.normalized_sha256,
        record_count=len(dataset.plumes),
        in_region_count=len(plumes_in_region(dataset.plumes, cfg.region)),
        seeded_source_count=seeded,
        uniform_fill_count=len(sources) - seeded,
    )
    return sources, ref


def generate_sources(
    cfg: ScenarioConfig,
    seed: int,
    plume_observations: Iterable[PlumeObservation] = (),
) -> tuple[Source, ...]:
    """Cluster verified plume inputs, then deterministically fill the registered source count.

    The checked-in EMIT-shaped fixture is explicitly synthetic and is never used as a real plume
    input. With no verified plume records, ``emit_fixture_then_uniform`` therefore takes its
    documented uniform-fill fallback and records unattributed source hypotheses.
    """
    if cfg.sources.placement == "emit_fixture_then_uniform":
        in_region = plumes_in_region(plume_observations, cfg.region)
        seeded = cluster_to_sources(in_region, cfg.sources.min_separation_m)
    else:
        seeded = []
    sources = list(seeded[: cfg.sources.count])
    if len(sources) == cfg.sources.count:
        return tuple(sources)

    try:
        from pyproj import Geod
    except ImportError as exc:  # pragma: no cover - covered by the geo CI extra
        raise RuntimeError("source placement requires the backend geo extra (pyproj)") from exc

    geod = Geod(ellps="WGS84")
    rng = keyed_rng(seed, "placement")
    lon_min, lat_min, lon_max, lat_max = cfg.region.bbox_wgs84
    sin_min, sin_max = math.sin(math.radians(lat_min)), math.sin(math.radians(lat_max))
    attempts = 0
    max_attempts = max(100_000, cfg.sources.count * 10_000)
    while len(sources) < cfg.sources.count:
        attempts += 1
        if attempts > max_attempts:
            raise RuntimeError(
                "could not place the configured source count while respecting min_separation_m"
            )
        lon = float(rng.uniform(lon_min, lon_max))
        lat = math.degrees(math.asin(float(rng.uniform(sin_min, sin_max))))
        if any(
            geod.inv(lon, lat, existing.lon, existing.lat)[2] < cfg.sources.min_separation_m
            for existing in sources
        ):
            continue
        index = len(sources) + 1
        sources.append(
            Source(id=f"source-{index:03d}", lon=lon, lat=lat, attribution_status="UNATTRIBUTED")
        )
    return tuple(sources)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _effective_bundle(bundle: ScenarioBundle, seed: int) -> ScenarioBundle:
    model_data = bundle.model.model_dump(mode="python")
    truth_data = bundle.truth.model_dump(mode="python")
    model_data["random_seed"] = seed
    truth_data["random_seed"] = seed
    return ScenarioBundle(
        model=ScenarioConfig.model_validate(model_data),
        truth=ScenarioConfig.model_validate(truth_data),
    )


def _windows_for(cfg: ScenarioConfig, sources: tuple[Source, ...], start: datetime, end: datetime):
    """Reuse geometry across policies in one process; the cache key covers every input."""
    key = (
        cfg.config_hash(),
        tuple((source.id, source.lon, source.lat) for source in sources),
        start,
        end,
        _ephemeris_sha256(),
    )
    cached = _WINDOW_CACHE.get(key)
    if cached is None:
        cached = tuple(generate_windows(cfg, list(sources), start, end))
        if len(_WINDOW_CACHE) >= 4:
            _WINDOW_CACHE.pop(next(iter(_WINDOW_CACHE)))
        _WINDOW_CACHE[key] = cached
    return tuple(revalidate_contract(window) for window in cached)


def _make_run_id(
    cfg: ScenarioConfig, truth_cfg: ScenarioConfig, policy: PolicyId, seed: int
) -> str:
    identity = {
        "scenario": cfg.scenario_id,
        "family": cfg.family,
        "policy": policy.value,
        "seed": seed,
        "model": cfg.config_hash(),
        "truth": truth_cfg.config_hash(),
        "code": __version__,
    }
    digest = hashlib.sha256(_canonical_json(identity)).hexdigest()[:16]
    return f"{cfg.scenario_id}-{policy.value}-{seed}-{digest}"


def _policy(policy_id: PolicyId, truth: TruthHistory):
    if policy_id is PolicyId.ORACLE:
        # This is the sole construction site for the truth-reading policy.
        from aether.evaluation.reference import OraclePolicy

        return OraclePolicy(truth)
    factories = {
        PolicyId.FIRST_FEASIBLE: FirstFeasible,
        PolicyId.LARGEST_FIRST: LargestFirst,
        PolicyId.STATIC_PRIORITY: StaticPriority,
        PolicyId.ADAPTIVE_EIG: AdaptiveEig,
        PolicyId.GREEDY_EIG: GreedyEig,
        PolicyId.RANDOM_FEASIBLE: RandomFeasible,
    }
    try:
        return factories[policy_id]()
    except KeyError as exc:
        raise ValueError(f"unsupported policy {policy_id.value!r}") from exc


def _pass_groups(windows: tuple[ObservationWindow, ...]):
    groups: dict[str, list[ObservationWindow]] = defaultdict(list)
    for window in windows:
        groups[window.pass_id].append(window)
    return {
        pass_id: (
            min(window.start_utc for window in items),
            max(window.end_utc for window in items),
            tuple(sorted(items, key=lambda item: (item.start_utc, item.id))),
        )
        for pass_id, items in groups.items()
    }


def _utilities(
    cfg: ScenarioConfig,
    windows: tuple[ObservationWindow, ...],
    beliefs: dict[str, SourceBelief],
    forecast: ForecastView,
    now_utc: datetime,
    revision: int,
    eval_times: list[datetime],
    pass_starts: dict[str, datetime],
) -> dict[str, CandidateUtility]:
    result = {}
    for window in windows:
        if not window.feasible or not window.options:
            continue
        sensor = cfg.sensors[window.sensor_id]
        spacecraft = cfg.spacecraft[window.spacecraft_id]
        belief = beliefs[window.source_id]
        choices = []
        for option in window.options:
            issue = forecast.latest_issue_time(now_utc)
            cloud = forecast.cloud_forecast(window.source_id, option.start_utc, issue)
            wind = forecast.wind_forecast(window.source_id, option.start_utc, issue)
            info = expected_info_gain_bits(
                belief,
                at_utc=option.start_utc,
                sensor=sensor,
                wind_forecast_m_s=wind,
                cloud_forecast=cloud,
                off_nadir_deg=option.off_nadir_deg,
                max_off_nadir_deg=spacecraft.attitude.max_off_nadir_deg,
            )
            next_pass = min(
                (
                    start
                    for pass_id, start in pass_starts.items()
                    if start > window.start_utc and pass_id != window.pass_id
                ),
                default=None,
            )
            decision = expected_brier_reduction(
                belief,
                at_utc=option.start_utc,
                eval_times=eval_times,
                next_pass_utc=next_pass,
                sensor=sensor,
                wind_forecast_m_s=wind,
                cloud_forecast=cloud,
                off_nadir_deg=option.off_nadir_deg,
                max_off_nadir_deg=spacecraft.attitude.max_off_nadir_deg,
            )
            valid = p_valid(
                sensor, cloud, option.off_nadir_deg, spacecraft.attitude.max_off_nadir_deg
            )
            latency_s = max(0.0, (option.start_utc - now_utc).total_seconds())
            resource_cost = (
                window.energy_wh / spacecraft.resources.battery_capacity_wh
                + window.data_bytes / spacecraft.resources.storage_bytes
            )
            weights = cfg.planner.weights
            utility = (
                weights["information"] * info
                + weights["decision"] * decision
                - weights["latency"] * latency_s
                - weights["resource"] * resource_cost
            )
            choices.append(
                (
                    utility,
                    option.start_utc,
                    option.option_id,
                    CandidateUtility(
                        window_id=window.id,
                        plan_revision=revision,
                        expected_info_gain_bits=info,
                        decision_relevance=decision,
                        latency_s=latency_s,
                        resource_cost=resource_cost,
                        p_valid_forecast=valid,
                        utility=utility,
                        integer_utility=int(round(utility * cfg.planner.utility_integer_scale)),
                    ),
                )
            )
        if choices:
            result[window.id] = max(
                choices, key=lambda item: (item[0], -item[1].timestamp(), item[2])
            )[3]
    return result


def run_policy(
    bundle: ScenarioBundle,
    policy_id: PolicyId | str,
    seed: int,
    *,
    plume_observations: Iterable[PlumeObservation] | None = None,
) -> RunRecord:
    """Run one deterministic, closed-loop policy; truth remains inside this function.

    Every persisted contract is revalidated at its boundary. Reproducible solver wall time is
    recorded as unavailable (``None``), since measuring it would make RunRecord bytes differ.
    """
    policy_id = PolicyId(policy_id)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    effective = _effective_bundle(bundle, seed)
    cfg, truth_cfg = effective.model, effective.truth
    sources, dataset_ref = resolve_sources(cfg, seed, plume_observations)
    truth = generate_truth(truth_cfg, sources, seed=seed)
    weather = build_synthetic_weather(truth_cfg, sources, model_cfg=cfg, seed=seed)
    forecast = weather.forecast_view()

    start_utc = cfg.simulation_epoch_utc
    end_utc = start_utc + timedelta(hours=cfg.horizon_hours)
    windows = _windows_for(cfg, sources, start_utc, end_utc)
    by_window = {window.id: window for window in windows}
    pass_groups = _pass_groups(tuple(window for window in windows if window.feasible))
    pass_starts = {pass_id: bounds[0] for pass_id, bounds in pass_groups.items()}
    pass_ends = {pass_id: bounds[1] for pass_id, bounds in pass_groups.items()}

    beliefs = {source.id: SourceBelief.prior(source.id, cfg) for source in sources}
    recorded_beliefs: list[BeliefSnapshot] = []
    plans: list[Plan] = []
    validations: list[ScheduleValidation] = []
    utilities_log: list[CandidateUtility] = []
    acquisitions = []
    events: list[RunEvent] = []
    run_id = _make_run_id(cfg, truth_cfg, policy_id, seed)
    model_hash, truth_hash = cfg.config_hash(), truth_cfg.config_hash()
    eval_instants = evaluation_times(
        start_utc, cfg.horizon_hours, cfg.evaluation.eval_interval_hours
    )
    eval_cursor = 0

    def emit(event_type: EventType, when: datetime, actor: str, payload: dict) -> None:
        sequence = len(events) + 1
        payload_bytes = _canonical_json(payload)
        event = RunEvent(
            event_id=f"{run_id}:event:{sequence:06d}",
            run_id=run_id,
            sequence_number=sequence,
            event_time_sim_utc=when,
            event_type=event_type,
            actor=actor,
            payload=payload,
            payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
            config_hash=model_hash,
            model_version="p0-0",
        )
        events.append(revalidate_contract(event))

    def predict_to(when: datetime) -> None:
        nonlocal beliefs
        for source_id in sorted(beliefs):
            beliefs[source_id] = beliefs[source_id].predict(when)

    def snapshot_all() -> None:
        for source_id in sorted(beliefs):
            recorded_beliefs.append(revalidate_contract(beliefs[source_id].snapshot()))

    emit(
        EventType.SCENARIO_CREATED,
        start_utc,
        "simulation",
        {"scenario_id": cfg.scenario_id, "family": cfg.family, "seed": seed},
    )
    emit(
        EventType.DATA_READY,
        start_utc,
        "source_generation",
        {
            "source_count": len(sources),
            "placement": cfg.sources.placement,
            "seeded_from_verified_plumes": sum(s.seeded_from_plume_id is not None for s in sources),
            "uniform_fallback_count": sum(s.seeded_from_plume_id is None for s in sources),
            "input_dataset": None if dataset_ref is None else dataset_ref.model_dump(mode="json"),
        },
    )
    emit(
        EventType.ORBIT_WINDOWS_READY,
        start_utc,
        "orbit",
        {
            "window_count": len(windows),
            "feasible_count": sum(window.feasible for window in windows),
            "ephemeris_sha256": _ephemeris_sha256(),
        },
    )
    for source_id in sorted(beliefs):
        recorded_beliefs.append(revalidate_contract(beliefs[source_id].snapshot()))
    emit(EventType.BELIEF_INITIALIZED, start_utc, "belief", {"source_count": len(beliefs)})

    policy = _policy(policy_id, truth)
    committed: dict[str, ObservationWindow] = {}
    committed_selection: dict[str, Selection] = {}
    frozen_passes: dict[str, tuple[str, ...]] = {}
    completed_passes: set[str] = set()
    executed_options: set[str] = set()
    current_plan: Plan | None = None
    current_plan_valid = False
    next_passes = set(pass_groups)
    forecast_events = _forecast_event_times(cfg)
    forecast_index = 0
    now = start_utc
    current_revision = 0
    pending_plan_cause = "initial"

    def make_plan(cause: str) -> None:
        nonlocal current_plan, current_plan_valid, current_revision
        candidate_list = []
        for window in windows:
            if (
                not window.feasible
                or window.pass_id in frozen_passes
                or window.pass_id in completed_passes
                or window.start_utc < now
                or window.start_utc > now + timedelta(hours=cfg.planner.lookahead_hours)
            ):
                continue
            candidate_list.append(window)
        candidate_windows = tuple(candidate_list)
        sensor_profile = next(iter(cfg.sensors.values()))
        remaining_option_count = sum(len(window.options) for window in candidate_windows)
        retry = 0
        while True:
            utils = _utilities(
                cfg,
                candidate_windows,
                beliefs,
                forecast,
                now,
                current_revision,
                eval_instants,
                pass_starts,
            )
            context = PlanningContext(
                run_id=run_id,
                revision=current_revision,
                now_utc=now,
                cause=cause,
                cfg=cfg,
                windows=candidate_windows,
                committed=tuple(committed[key] for key in sorted(committed)),
                utilities=FrozenDict(utils),
                posterior_mean_flux_kg_h=FrozenDict(
                    {sid: belief.posterior_mean_flux_kg_h() for sid, belief in beliefs.items()}
                ),
                p_active_by_source=FrozenDict(
                    {sid: belief.p_active() for sid, belief in beliefs.items()}
                ),
                committed_selections=tuple(
                    committed_selection[key] for key in sorted(committed_selection)
                ),
            )
            emit(
                EventType.PLAN_REQUESTED,
                now,
                "simulation",
                {"revision": current_revision, "cause": cause, "checker_retry": retry},
            )
            proposed = revalidate_contract(policy.plan(context))
            if not isinstance(proposed, Plan):
                raise TypeError("policy returned a non-Plan value")
            # Wall-clock solver time is not reproducible output and is deliberately unavailable.
            proposed = revalidate_contract(proposed.model_copy(update={"runtime_s": None}))
            if proposed.run_id != run_id or proposed.policy_id is not policy_id:
                raise ValueError("policy plan identity does not match the active run")
            if proposed.revision != current_revision or proposed.created_at_sim_utc != now:
                raise ValueError("policy plan revision/time does not match its PlanningContext")
            if len({window.sensor_id for window in candidate_windows}) > 1:
                raise NotImplementedError(
                    "runner integration currently requires one sensor profile"
                )
            emit(
                EventType.PLAN_PROPOSED,
                now,
                policy_id.value,
                {
                    "revision": current_revision,
                    "checker_retry": retry,
                    "candidate_count": len(candidate_windows),
                    "selections": [
                        selection.model_dump(mode="json") for selection in proposed.selections
                    ],
                    "solver_status": proposed.solver_status.value,
                },
            )
            report = revalidate_contract(
                check_schedule(
                    proposed,
                    tuple(window for window in windows if window.id not in committed),
                    sources,
                    cfg.spacecraft,
                    sensor_profile,
                    cfg,
                    committed=tuple(committed[key] for key in sorted(committed)),
                    committed_selections=tuple(
                        committed_selection[key] for key in sorted(committed_selection)
                    ),
                )
            )
            if not isinstance(report, ScheduleValidation):
                raise TypeError("independent checker returned an invalid report")
            emit(
                EventType.PLAN_VALIDATED,
                now,
                "independent_checker",
                {
                    "revision": current_revision,
                    "checker_retry": retry,
                    "ok": report.ok,
                    "violations": [
                        violation.model_dump(mode="json") for violation in report.violations
                    ],
                },
            )
            if report.ok:
                validations.append(report)
                utilities_log.extend(revalidate_contract(item) for item in utils.values())
                proposed = revalidate_contract(proposed.model_copy(update={"validation_ok": True}))
                plans.append(proposed)
                current_plan, current_plan_valid = proposed, True
                break

            if retry >= remaining_option_count:
                raise RuntimeError("checker violations remain after exhausting candidate options")
            failed_ids = {
                option_id for violation in report.violations for option_id in violation.option_ids
            }
            selected = [
                selection
                for selection in proposed.selections
                if not failed_ids or selection.option_id in failed_ids
            ]
            if not selected:
                raise RuntimeError(
                    "independent checker rejected a plan without identifying a removable selection"
                )
            selected.sort(
                key=lambda selection: (
                    utils.get(selection.window_id).utility
                    if utils.get(selection.window_id) is not None
                    else float("inf"),
                    selection.option_id,
                )
            )
            remove_id = selected[0].option_id
            candidate_windows = tuple(
                revalidate_contract(
                    window.model_copy(
                        update={
                            "options": tuple(
                                option for option in window.options if option.option_id != remove_id
                            )
                        }
                    )
                )
                for window in candidate_windows
                if any(option.option_id != remove_id for option in window.options)
                or all(option.option_id != remove_id for option in window.options)
            )
            emit(
                EventType.PLAN_REJECTED,
                now,
                "simulation",
                {
                    "revision": current_revision,
                    "checker_retry": retry,
                    "reason": "independent_checker_violation",
                    "removed_option_id": remove_id,
                    "violations": [
                        violation.model_dump(mode="json") for violation in report.violations
                    ],
                },
            )
            retry += 1
        current_revision += 1

    def freeze_pass(pass_id: str) -> None:
        if pass_id in frozen_passes or pass_id in completed_passes:
            return
        selected = ()
        if current_plan is not None and current_plan_valid:
            selected = tuple(
                selection
                for selection in current_plan.selections
                if by_window[selection.window_id].pass_id == pass_id
            )
        frozen_passes[pass_id] = tuple(selection.window_id for selection in selected)
        for selection in selected:
            window = by_window[selection.window_id]
            committed[window.id] = window
            committed_selection[window.id] = selection

    def replan(cause: str) -> None:
        emit(EventType.REPLAN_REQUESTED, now, "simulation", {"cause": cause})
        make_plan(cause)

    make_plan("initial")
    triggers = set(cfg.planner.replan_on)
    while now < end_utc:
        pending_times = []
        if forecast_index < len(forecast_events):
            pending_times.append(forecast_events[forecast_index][0])
        pending_times.extend(pass_starts[pid] for pid in next_passes)
        for pass_id, window_ids in frozen_passes.items():
            pending_times.append(pass_ends[pass_id])
            for window_id in window_ids:
                if window_id not in executed_options:
                    selection = committed_selection[window_id]
                    window = by_window[window_id]
                    option = next(o for o in window.options if o.option_id == selection.option_id)
                    pending_times.append(option.start_utc)
        if not pending_times:
            break
        next_time = min(pending_times)
        if next_time < now:
            raise RuntimeError(f"simulation event moved backwards from {now} to {next_time}")
        while eval_cursor < len(eval_instants) and eval_instants[eval_cursor] <= next_time:
            eval_time = eval_instants[eval_cursor]
            predict_to(eval_time)
            snapshot_all()
            eval_cursor += 1
        predict_to(next_time)
        now = next_time

        completed_now = [pass_id for pass_id in frozen_passes if pass_ends[pass_id] == now]
        for pass_id in sorted(completed_now):
            for window_id in frozen_passes.pop(pass_id):
                # Already committed selections remain fixed after execution.
                committed[window_id] = by_window[window_id]
            completed_passes.add(pass_id)
            next_passes.discard(pass_id)
        should_replan = bool(completed_now and "pass_completed" in triggers)

        if forecast_index < len(forecast_events) and forecast_events[forecast_index][0] == now:
            _, payload = forecast_events[forecast_index]
            forecast_index += 1
            emit(EventType.FORECAST_REVISED, now, "weather", payload)
            if "forecast_revision" in triggers:
                should_replan = True
                pending_plan_cause = "forecast_revision"

        if should_replan:
            replan(
                pending_plan_cause
                if pending_plan_cause == "forecast_revision"
                else "pass_completed"
            )
            pending_plan_cause = "pass_completed"

        starts_now = sorted(pid for pid in next_passes if pass_starts[pid] == now)
        for pass_id in starts_now:
            next_passes.discard(pass_id)
            freeze_pass(pass_id)
            # If the pass has no selected option, it still runs to its geometric end so the
            # configured pass-completed trigger advances the loop deterministically.

        acquisitions_now = []
        for pass_id, window_ids in frozen_passes.items():
            for window_id in window_ids:
                if window_id in executed_options:
                    continue
                selection = committed_selection[window_id]
                window = by_window[window_id]
                option = next(o for o in window.options if o.option_id == selection.option_id)
                if option.start_utc == now:
                    acquisitions_now.append(
                        (option.start_utc, option.option_id, pass_id, window, option)
                    )
        informative = False
        for _, _, _pass_id, window, option in sorted(acquisitions_now):
            acquisition = revalidate_contract(
                sample_outcome(
                    window,
                    option.start_utc,
                    truth,
                    weather,
                    truth_cfg.sensors[window.sensor_id],
                    seed,
                    option=option,
                    spacecraft_truth=truth_cfg.spacecraft[window.spacecraft_id],
                )
            )
            if acquisition.option_id != option.option_id:
                raise ValueError("outcome option identity changed at the simulation boundary")
            acquisitions.append(acquisition)
            executed_options.add(window.id)
            emit(
                EventType.OBSERVATION_WINDOW_EXECUTED,
                now,
                "simulator",
                {
                    "acquisition_id": acquisition.id,
                    "window_id": window.id,
                    "option_id": option.option_id,
                    "outcome": acquisition.outcome.value,
                },
            )
            prior = beliefs[window.source_id]
            predicted = prior.predict(now)
            beliefs[window.source_id] = predicted.update(
                acquisition, sensor=cfg.sensors[window.sensor_id]
            )
            updated = acquisition.outcome in {
                ObservationOutcome.DETECTION,
                ObservationOutcome.VALID_NON_DETECTION,
            }
            informative = informative or updated
            recorded_beliefs.append(revalidate_contract(beliefs[window.source_id].snapshot()))
            emit(
                EventType.BELIEF_UPDATED if updated else EventType.BELIEF_PREDICTED,
                now,
                "belief",
                {
                    "source_id": window.source_id,
                    "acquisition_id": acquisition.id,
                    "evidence_added": updated,
                },
            )
        if informative and "informative_acquisition" in triggers:
            replan("informative_acquisition")
            pending_plan_cause = "pass_completed"

    while eval_cursor < len(eval_instants):
        eval_time = eval_instants[eval_cursor]
        predict_to(eval_time)
        snapshot_all()
        eval_cursor += 1

    emit(
        EventType.RUN_COMPLETED,
        end_utc,
        "simulation",
        {"plan_count": len(plans), "acquisition_count": len(acquisitions)},
    )
    run = RunRecord(
        run_id=run_id,
        policy_id=policy_id,
        scenario_id=cfg.scenario_id,
        family=cfg.family,
        seed=seed,
        model_config_hash=model_hash,
        truth_config_hash=truth_hash,
        code_version=__version__,
        sources=sources,
        windows=windows,
        plans=tuple(plans),
        validations=tuple(validations),
        utilities=tuple(utilities_log),
        acquisitions=tuple(acquisitions),
        beliefs=tuple(recorded_beliefs),
        events=tuple(events),
        input_dataset=dataset_ref,
    )
    return revalidate_contract(run)


def _forecast_event_times(cfg: ScenarioConfig) -> list[tuple[datetime, dict]]:
    interval = cfg.weather.forecast.issue_interval_hours
    event_map: dict[datetime, dict] = {}
    issue_hour = interval
    while issue_hour < cfg.horizon_hours:
        when = cfg.simulation_epoch_utc + timedelta(hours=issue_hour)
        event_map[when] = {"issue_time_utc": when.isoformat(), "injected": False}
        issue_hour += interval
    for event in cfg.weather.injected_events:
        when = cfg.simulation_epoch_utc + timedelta(hours=event.at_hour)
        if when >= cfg.simulation_epoch_utc + timedelta(hours=cfg.horizon_hours):
            continue
        existing = event_map.get(when, {})
        event_map[when] = {
            **existing,
            "issue_time_utc": forecast_time_text(when),
            "injected": True,
            "kind": event.kind,
            "target_source_index": event.target_source_index,
            "cloud_fraction": event.cloud_fraction,
            "duration_hours": event.duration_hours,
        }
    return sorted(event_map.items())


def forecast_time_text(when: datetime) -> str:
    return when.isoformat().replace("+00:00", "Z")


def _ephemeris_sha256() -> str:
    manifest_path = repo_root() / "data/ephemeris/manifest.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("the pinned DE421 manifest is required for a simulation run") from exc
    digest = data.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("pinned DE421 manifest has no valid SHA-256")
    return digest


__all__ = [
    "generate_sources",
    "load_configured_dataset",
    "repo_root",
    "resolve_sources",
    "run_policy",
]
