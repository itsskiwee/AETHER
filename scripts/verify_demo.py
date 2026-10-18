"""Acceptance checks over real offline demo artifacts; never creates example records."""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
from aether.belief import SourceBelief
from aether.config import load_scenario
from aether.contracts import ObservationOutcome, RunRecord
from aether.evaluation.metrics import evaluation_times


def verify(root: Path, family: str | None = None) -> None:
    paths = sorted(root.glob("*/run.json"))
    if len(paths) != 2:
        raise ValueError(f"expected two real policy runs, found {len(paths)}")
    summaries = []
    policies = set()
    for path in paths:
        run = RunRecord.model_validate_json(path.read_bytes())
        policies.add(run.policy_id.value)
        cfg = load_scenario("configs/demo.yaml", family, seed=run.seed).model
        assert run.seed == 1000
        assert run.model_config_hash == cfg.config_hash()
        assert {p.revision for p in run.plans} == {
            v.plan_revision for v in run.validations
        }
        assert len(run.plans) == len(run.validations)
        assert all(v.ok and not v.violations for v in run.validations)
        assert all(p.validation_ok for p in run.plans)
        assert all(p.runtime_s is None for p in run.plans)
        windows = {w.id: w for w in run.windows}
        assert run.acquisitions
        assert list(run.acquisitions) == sorted(
            run.acquisitions, key=lambda a: (a.time_utc, a.option_id)
        )
        # Reconstruct the inference path from observation contracts only. Missing outcomes
        # must preserve the predicted tensor/evidence, while valid outcomes add evidence.
        beliefs = {s.id: SourceBelief.prior(s.id, cfg) for s in run.sources}
        for acq in run.acquisitions:
            prior = beliefs[acq.source_id].predict(acq.time_utc)
            posterior = prior.update(acq, sensor=cfg.sensors[acq.sensor_id])
            informative = acq.outcome in {
                ObservationOutcome.DETECTION,
                ObservationOutcome.VALID_NON_DETECTION,
            }
            assert (
                posterior.evidence_ids == (*prior.evidence_ids, acq.id)
                if informative
                else posterior.evidence_ids == prior.evidence_ids
            )
            if not informative:
                assert (prior.tensor == posterior.tensor).all()
            expected = posterior.snapshot()
            matches = [
                b
                for b in run.beliefs
                if b.source_id == acq.source_id
                and b.state_time_utc == acq.time_utc
                and b.evidence_ids == expected.evidence_ids
            ]
            assert matches
            actual = matches[-1]
            assert actual.received_new_evidence == informative
            regimes = sorted(expected.regime_probs, key=lambda regime: regime.value)
            np.testing.assert_allclose(
                [
                    actual.p_active,
                    actual.flux_median_kg_h,
                    *actual.flux_ci90_kg_h,
                    actual.entropy_bits,
                    *(actual.regime_probs[regime] for regime in regimes),
                ],
                [
                    expected.p_active,
                    expected.flux_median_kg_h,
                    *expected.flux_ci90_kg_h,
                    expected.entropy_bits,
                    *(expected.regime_probs[regime] for regime in regimes),
                ],
                rtol=1e-12,
                atol=1e-12,
            )
            beliefs[acq.source_id] = posterior
            option = next(
                o
                for o in windows[acq.window_id].options
                if o.option_id == acq.option_id
            )
            assert acq.time_utc == option.start_utc
        for instant in evaluation_times(
            cfg.simulation_epoch_utc,
            cfg.horizon_hours,
            cfg.evaluation.eval_interval_hours,
        ):
            assert {
                b.source_id for b in run.beliefs if b.state_time_utc == instant
            } == set(beliefs)
        injections = [
            e
            for e in run.events
            if e.event_type.value == "FORECAST_REVISED" and e.payload.get("injected")
        ]
        assert len(injections) == 1
        event = injections[0]
        after = next(
            p
            for p in run.plans
            if p.created_at_sim_utc == event.event_time_sim_utc
            and p.cause == "forecast_revision"
        )
        before = max(
            (p for p in run.plans if p.revision < after.revision),
            key=lambda p: p.revision,
        )
        before_ids = {s.option_id for s in before.selections}
        after_ids = {s.option_id for s in after.selections}
        replay = root / "replay" / run.run_id / "run.json"
        assert replay.read_bytes() == path.read_bytes(), (
            f"{run.policy_id}: replay differs"
        )
        with zipfile.ZipFile(root / f"{run.run_id}.zip") as archive:
            exported = archive.read("run.json")
            manifest = json.loads(archive.read("manifest.json"))
        assert RunRecord.model_validate_json(exported) == run
        assert manifest["run_json_sha256"] == hashlib.sha256(exported).hexdigest()
        summary = {
            "policy": run.policy_id.value,
            "seed": run.seed,
            "plans": len(run.plans),
            "checker_violations": 0,
            "acquisitions": len(run.acquisitions),
            "outcomes": dict(Counter(a.outcome.value for a in run.acquisitions)),
            "evaluation_times": len(
                evaluation_times(
                    cfg.simulation_epoch_utc,
                    cfg.horizon_hours,
                    cfg.evaluation.eval_interval_hours,
                )
            ),
            "forecast_revision": after.revision,
            "forecast_time_utc": event.event_time_sim_utc.isoformat(),
            "forecast_removed_option_ids": sorted(before_ids - after_ids),
            "forecast_added_option_ids": sorted(after_ids - before_ids),
            "forecast_selections_changed": before_ids != after_ids,
            "canonical_json_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "replay_identical": True,
            "export_reload_verified": True,
        }
        summaries.append(summary)
        print(
            f"{run.policy_id.value}: {len(run.plans)} checked plans, {len(run.acquisitions)} acquisitions; forecast selections changed: {before_ids != after_ids}",
            flush=True,
        )
    assert policies == {"largest_first", "adaptive_eig"}
    (root / "acceptance.json").write_text(
        json.dumps(
            {
                "label": "SIMULATED MISSION — offline replay",
                "config": "configs/demo.yaml",
                "note": "Forecast differences describe consecutive recorded plans, not a causal policy-performance estimate.",
                "runs": summaries,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    verify(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else None)
