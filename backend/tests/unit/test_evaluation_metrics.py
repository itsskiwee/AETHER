"""EVL-01 / EVL-02: every metric checked against hand-computed values on a 2-source, 12-hour run.

Fixture (t0 = simulation epoch, evaluation every 6 h -> times t0 and t0+6h):

    source A: PERSISTENT, static flux 300 kg/h, active all 12 h  -> mean rate 300 (high-impact)
    source B: EPISODIC,   static flux 100 kg/h, active hours 0-2 -> mean rate 25

    beliefs        t0: p_A=0.5 ci_A=(200,400)   p_B=0.5 ci_B=(150,400)
                 t0+6: p_A=0.9 ci_A=(200,400)   p_B=0.2 ci_B=(50,200)
    truth z        t0: z_A=1  z_B=1           t0+6: z_A=1  z_B=0
    acquisitions   A: DETECTION   B: INVALID_ACQUISITION
"""

import math
from datetime import timedelta

import numpy as np
import pytest

from aether.config import load_scenario
from aether.contracts import (
    BeliefSnapshot,
    ObservationOutcome,
    Plan,
    PolicyId,
    Regime,
    RunRecord,
    ScheduleValidation,
    ScheduleViolation,
    SimulatedAcquisition,
    SolverStatus,
    Source,
)
from aether.evaluation import metrics
from aether.simulation.truth_types import SourceTruth, TruthHistory


@pytest.fixture(scope="module")
def cfg(base_config_path):
    return load_scenario(base_config_path).model.model_copy(update={"horizon_hours": 12.0})


def _belief(sid, t, p, ci, regimes=None):
    regimes = regimes or {
        Regime.PERSISTENT: 1 / 3,
        Regime.INTERMITTENT: 1 / 3,
        Regime.EPISODIC: 1 / 3,
    }
    return BeliefSnapshot(
        source_id=sid,
        state_time_utc=t,
        p_active=p,
        regime_probs=regimes,
        flux_median_kg_h=(ci[0] * ci[1]) ** 0.5,
        flux_ci90_kg_h=ci,
        entropy_bits=0.5,
        model_version="test",
        evidence_ids=(),
        received_new_evidence=False,
    )


def _acq(sid, t, outcome):
    return SimulatedAcquisition(
        id=f"acq-{sid}",
        option_id=f"w-{sid}#0",
        window_id=f"w-{sid}",
        source_id=sid,
        spacecraft_id="vsat_a",
        sensor_id="vs_a_point_source",
        time_utc=t,
        outcome=outcome,
        measured_flux_kg_h=300.0 if outcome is ObservationOutcome.DETECTION else None,
        off_nadir_deg=10.0,
        wind_estimate_m_s=4.0,
        scene_cloud_fraction=0.1,
        rng_key="k",
    )


def _run(cfg, beliefs, acquisitions=(), plans=(), validations=()):
    return RunRecord(
        run_id="r1",
        policy_id=PolicyId.ADAPTIVE_EIG,
        scenario_id=cfg.scenario_id,
        family=cfg.family,
        seed=1000,
        model_config_hash="m",
        truth_config_hash="t",
        code_version="test",
        sources=(Source(id="A", lon=-103.0, lat=32.0), Source(id="B", lon=-102.0, lat=32.5)),
        windows=(),
        plans=plans,
        validations=validations,
        utilities=(),
        acquisitions=tuple(acquisitions),
        beliefs=tuple(beliefs),
        events=(),
    )


@pytest.fixture(scope="module")
def truth(cfg):
    b_active = np.zeros(12, bool)
    b_active[:3] = True
    return TruthHistory(
        epoch_utc=cfg.simulation_epoch_utc,
        hours=12,
        sources={
            "A": SourceTruth(
                source_id="A",
                regime=Regime.PERSISTENT,
                median_flux_kg_h=300.0,
                active=np.ones(12, bool),
                flux_kg_h=np.full(12, 300.0),
            ),
            "B": SourceTruth(
                source_id="B",
                regime=Regime.EPISODIC,
                median_flux_kg_h=100.0,
                active=b_active,
                flux_kg_h=np.where(b_active, 100.0, 0.0),
            ),
        },
    )


@pytest.fixture(scope="module")
def run(cfg):
    t0 = cfg.simulation_epoch_utc
    t6 = t0 + timedelta(hours=6)
    beliefs = [
        _belief("A", t0, 0.5, (200.0, 400.0)),
        _belief("B", t0, 0.5, (150.0, 400.0)),
        _belief("A", t6, 0.9, (200.0, 400.0)),
        _belief("B", t6, 0.2, (50.0, 200.0)),
    ]
    acqs = [
        _acq("A", t0 + timedelta(hours=3), ObservationOutcome.DETECTION),
        _acq("B", t0 + timedelta(hours=3), ObservationOutcome.INVALID_ACQUISITION),
    ]
    return _run(cfg, beliefs, acqs)


@pytest.fixture(scope="module")
def scores(run, truth, cfg):
    return metrics.score_run(run, truth, cfg)


def test_evaluation_times_exclude_horizon(cfg):
    t0 = cfg.simulation_epoch_utc
    assert metrics.evaluation_times(t0, 12, 6) == [t0, t0 + timedelta(hours=6)]
    assert len(metrics.evaluation_times(t0, 72, 6)) == 12


def test_brier(scores):
    # (0.5-1)^2 + (0.5-1)^2 + (0.9-1)^2 + (0.2-0)^2 = 0.25+0.25+0.01+0.04 = 0.55 -> / 4
    assert scores["brier_active_state"] == pytest.approx(0.1375, abs=1e-12)
    assert scores["n_points"] == 4


def test_log_loss(scores):
    expected = -(math.log(0.5) * 2 + math.log(0.9) + math.log(0.8)) / 4
    assert scores["log_loss_active_state"] == pytest.approx(expected, abs=1e-12)


def test_log_loss_clips_certain_wrong_prediction():
    pt = metrics._Point("A", 0.0, 0.0, 1, (1.0, 2.0))
    assert metrics.log_loss([pt]) == pytest.approx(-math.log(metrics.LOG_LOSS_CLIP))


def test_ece(scores):
    # bin 5: two points p=0.5, z=1 -> 0.5 * 2/4; bin 9: |0.9-1| * 1/4; bin 2: |0.2-0| * 1/4
    assert scores["ece_active_state"] == pytest.approx(0.25 + 0.025 + 0.05, abs=1e-12)


def test_ece_puts_probability_one_in_top_bin():
    pts = [metrics._Point("A", 0.0, 1.0, 1, (1.0, 2.0))]
    assert metrics.ece(pts) == pytest.approx(0.0)


def test_flux_coverage(scores):
    # A covers 300 twice; B misses 100 with (150,400), covers with (50,200)
    assert scores["flux_interval_coverage_90"] == pytest.approx(0.75)


def test_regime_breakdown(scores):
    assert scores["brier_active_state[regime=PERSISTENT]"] == pytest.approx(0.13)
    assert scores["brier_active_state[regime=EPISODIC]"] == pytest.approx(0.145)
    assert scores["brier_active_state[regime=INTERMITTENT]"] is None
    assert scores["n_points[regime=INTERMITTENT]"] == 0


def test_observed_breakdown_counts_only_evidence(scores):
    # B's only acquisition was INVALID: it is not "observed"
    assert scores["n_sources[observed=yes]"] == 1
    assert scores["brier_active_state[observed=yes]"] == pytest.approx(0.13)
    assert scores["brier_active_state[observed=no]"] == pytest.approx(0.145)


def test_corroboration_is_right_censored(scores):
    # A: P(Z=1)=0.9 at t0+6h -> 6 h. B: P(true state) = 0.5, 0.8 -> never -> censored at 12 h
    assert scores["corroborated_sources"] == 1
    assert scores["censored_sources"] == 1
    assert scores["time_to_corroboration_hours"] == pytest.approx((6 + 12) / 2)


def test_corroboration_tracks_changing_true_state():
    pts = [metrics._Point("B", 0.0, 0.95, 1, (1, 2)), metrics._Point("B", 6.0, 0.95, 0, (1, 2))]
    assert metrics.corroboration(pts, 0.9, 12.0).hours_by_source == {"B": 0.0}
    pts = [metrics._Point("B", 0.0, 0.5, 1, (1, 2)), metrics._Point("B", 6.0, 0.05, 0, (1, 2))]
    assert metrics.corroboration(pts, 0.9, 12.0).hours_by_source == {"B": 6.0}


def test_high_impact_recall(scores, truth, cfg):
    assert metrics.high_impact_sources(truth, 278.0) == {"A"}
    assert scores["n_high_impact_sources"] == 1
    assert scores["high_impact_recall_at_5"] == 1.0


def test_high_impact_recall_top1_uses_long_run_rate(run, truth, cfg):
    t6 = cfg.simulation_epoch_utc + timedelta(hours=6)
    # Make B look persistent and large; A look episodic: top-1 is then B and recall is 0.
    beliefs = list(run.beliefs) + [
        _belief(
            "A",
            t6,
            0.9,
            (10.0, 40.0),
            {Regime.EPISODIC: 1.0, Regime.PERSISTENT: 0.0, Regime.INTERMITTENT: 0.0},
        ),
        _belief(
            "B",
            t6,
            0.2,
            (900.0, 1100.0),
            {Regime.PERSISTENT: 1.0, Regime.EPISODIC: 0.0, Regime.INTERMITTENT: 0.0},
        ),
    ]
    r = _run(cfg, beliefs)
    recall, n = metrics.high_impact_recall_at_k(r, truth, cfg, t6, k=1)
    assert (recall, n) == (0.0, 1)


def test_high_impact_recall_undefined_without_high_impact_sources(run, truth, cfg):
    strict = cfg.model_copy(
        update={"evaluation": cfg.evaluation.model_copy(update={"high_impact_mean_rate_kg_h": 1e6})}
    )
    recall, n = metrics.high_impact_recall_at_k(run, truth, strict, cfg.simulation_epoch_utc)
    assert recall is None and n == 0


def test_expected_mean_rate(cfg):
    snap = _belief(
        "A",
        cfg.simulation_epoch_utc,
        0.5,
        (100.0, 400.0),
        {Regime.PERSISTENT: 1.0, Regime.INTERMITTENT: 0.0, Regime.EPISODIC: 0.0},
    )
    pi = 240 / (240 + 48)  # persistent stationary fraction from base.yaml
    assert metrics.expected_mean_rate_kg_h(snap, cfg) == pytest.approx(pi * 200.0)


def test_acquisition_counts(scores):
    assert scores["acquisitions_count"] == 2
    assert scores["valid_acquisitions_count"] == 1
    assert scores["valid_acquisition_fraction"] == 0.5


def test_no_plans_means_undefined_runtime(scores):
    assert scores["solver_runtime_p95_s"] is None
    assert scores["plans_without_validation"] == 0


def test_checker_accounting(run, cfg):
    t0 = cfg.simulation_epoch_utc
    plans = tuple(
        Plan(
            run_id="r1",
            policy_id=PolicyId.ADAPTIVE_EIG,
            revision=rev,
            created_at_sim_utc=t0,
            cause="test",
            objective_weights={},
            candidate_window_ids=(),
            selected_option_ids=(),
            solver_status=SolverStatus.OPTIMAL,
            objective_value=0.0,
            best_bound=0.0,
            runtime_s=rt,
        )
        for rev, rt in ((0, 1.0), (1, 3.0), (2, 2.0))
    )
    validations = (
        ScheduleValidation(plan_revision=0, ok=True, violations=(), checker_version="t"),
        ScheduleValidation(
            plan_revision=1,
            ok=False,
            checker_version="t",
            violations=(
                ScheduleViolation(option_ids=("w#0", "w2#0"), rule="SLEW", detail="x"),
                ScheduleViolation(option_ids=("w#0",), rule="STORAGE", detail="y"),
            ),
        ),
    )
    out = metrics.solver_and_checker(_run(cfg, run.beliefs, plans=plans, validations=validations))
    assert out["feasibility_checker_violations"] == 2
    assert out["plans_failing_validation"] == 1
    assert out["plans_without_validation"] == 1
    assert out["solver_runtime_p95_s"] == pytest.approx(np.percentile([1.0, 3.0, 2.0], 95))


def test_missing_snapshot_raises(run, truth, cfg):
    r = _run(cfg, run.beliefs[:3])
    with pytest.raises(ValueError, match="no belief snapshot for B"):
        metrics.score_run(r, truth, cfg)


def test_last_snapshot_wins(run, truth, cfg):
    t6 = cfg.simulation_epoch_utc + timedelta(hours=6)
    r = _run(cfg, list(run.beliefs) + [_belief("B", t6, 0.0, (50.0, 200.0))])
    # B at t6 now contributes (0-0)^2 instead of 0.04
    assert metrics.score_run(r, truth, cfg)["brier_active_state"] == pytest.approx(0.51 / 4)


def test_source_mismatch_raises(run, truth, cfg):
    bad = truth.model_copy(update={"sources": {"A": truth.sources["A"]}})
    with pytest.raises(ValueError, match="disagree on sources"):
        metrics.score_run(run, bad, cfg)
