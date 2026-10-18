from datetime import UTC, datetime

import numpy as np
import pytest
from pydantic import ValidationError

from aether.contracts import (
    AcquisitionOption,
    BeliefSnapshot,
    ObservationOutcome,
    ObservationWindow,
    SimulatedAcquisition,
    acquisition_option_id,
)
from aether.rng import derive_seed, keyed_rng

T0 = datetime(2026, 10, 17, tzinfo=UTC)


def _acq(**kw):
    base = dict(
        id="a1",
        option_id="w1#0",
        window_id="w1",
        source_id="s1",
        spacecraft_id="vsat_a",
        sensor_id="vs_a_point_source",
        time_utc=datetime(2026, 10, 17, tzinfo=UTC),
        outcome=ObservationOutcome.VALID_NON_DETECTION,
        measured_flux_kg_h=None,
        off_nadir_deg=12.0,
        wind_estimate_m_s=3.0,
        scene_cloud_fraction=0.1,
        rng_key="k",
    )
    base.update(kw)
    return SimulatedAcquisition(**base)


def test_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        _acq(time_utc=datetime(2026, 10, 17))


def test_non_detection_cannot_carry_flux():
    with pytest.raises(ValidationError):
        _acq(measured_flux_kg_h=100.0)


def test_simulated_cannot_claim_real_provenance():
    with pytest.raises(ValidationError):
        _acq(provenance_class="REAL_OBSERVATION")


def test_contracts_are_frozen():
    with pytest.raises(ValidationError):
        _acq().outcome = ObservationOutcome.DETECTION


def test_keyed_rng_reproducible_and_independent():
    a = keyed_rng(1, "outcome", "s1", "vs_a", "2026-10-17T00:00:00+00:00").random(4)
    b = keyed_rng(1, "outcome", "s1", "vs_a", "2026-10-17T00:00:00+00:00").random(4)
    c = keyed_rng(1, "outcome", "s2", "vs_a", "2026-10-17T00:00:00+00:00").random(4)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_unregistered_namespace_rejected():
    with pytest.raises(ValueError):
        keyed_rng(1, "planner_peek")


def test_acquisition_carries_no_true_environment():
    """lessons.md 2.4: the planner side must never receive true wind."""
    assert "wind_m_s" not in SimulatedAcquisition.model_fields
    assert "wind_estimate_m_s" in SimulatedAcquisition.model_fields


def test_option_requires_unit_los_and_id_format():
    good = dict(
        option_id=acquisition_option_id("w1", T0),
        window_id="w1",
        start_utc=T0,
        end_utc=T0.replace(second=3),
        off_nadir_deg=5.0,
        sun_elevation_deg=40.0,
        los_unit_ecef=(1.0, 0.0, 0.0),
    )
    assert AcquisitionOption(**good).end_los_unit_ecef is None
    with_end = AcquisitionOption(**{**good, "end_los_unit_ecef": (0.0, 1.0, 0.0)})
    assert AcquisitionOption.model_validate_json(with_end.model_dump_json()) == with_end
    with pytest.raises(ValidationError):
        AcquisitionOption(**{**good, "end_los_unit_ecef": (2.0, 0.0, 0.0)})
    with pytest.raises(ValidationError):
        AcquisitionOption(**{**good, "los_unit_ecef": (2.0, 0.0, 0.0)})
    with pytest.raises(ValidationError):
        AcquisitionOption(**{**good, "option_id": "w1-0"})


def test_window_rejects_options_with_the_same_start_time():
    option = AcquisitionOption(
        option_id=acquisition_option_id("w1", T0),
        window_id="w1",
        start_utc=T0,
        end_utc=T0.replace(second=3),
        off_nadir_deg=5.0,
        sun_elevation_deg=40.0,
        los_unit_ecef=(1.0, 0.0, 0.0),
    )
    with pytest.raises(ValidationError, match="option IDs must be unique"):
        ObservationWindow(
            id="w1",
            spacecraft_id="sat",
            sensor_id="sensor",
            source_id="s1",
            start_utc=T0,
            end_utc=T0.replace(second=3),
            pass_id="pass",
            orbit_number=1,
            feasible=True,
            min_off_nadir_deg=5.0,
            options=(option, option),
            duration_s=3.0,
            energy_wh=1.0,
            data_bytes=1,
        )


def test_belief_snapshot_coherence():
    good = dict(
        source_id="s1",
        state_time_utc=T0,
        p_active=0.3,
        regime_probs={"PERSISTENT": 0.2, "INTERMITTENT": 0.5, "EPISODIC": 0.3},
        flux_median_kg_h=300.0,
        flux_ci90_kg_h=(80.0, 1500.0),
        entropy_bits=0.88,
        model_version="t",
        evidence_ids=(),
        received_new_evidence=False,
    )
    BeliefSnapshot(**good)
    with pytest.raises(ValidationError):
        BeliefSnapshot(**{**good, "regime_probs": {"PERSISTENT": 0.9, "EPISODIC": 0.3}})
    with pytest.raises(ValidationError):
        BeliefSnapshot(**{**good, "flux_ci90_kg_h": (500.0, 1500.0)})


def test_derive_seed_is_stable_and_bounded():
    a = derive_seed(1000, "solver", "adaptive_eig", 3)
    assert a == derive_seed(1000, "solver", "adaptive_eig", 3)
    assert 0 <= a < 2**31 - 1
    assert a != derive_seed(1001, "solver", "adaptive_eig", 3)


def test_bootstrap_namespace_registered():
    """L3 contract request: EVL-03 paired_bootstrap needs a keyed stream."""
    a = keyed_rng(7, "bootstrap", "adaptive_eig_vs_largest_first").integers(0, 100, 5)
    b = keyed_rng(7, "bootstrap", "adaptive_eig_vs_largest_first").integers(0, 100, 5)
    assert np.array_equal(a, b)


def _data_source(**kw):
    from aether.contracts.models import DataSource

    base = dict(
        provider="NASA LP DAAC",
        dataset="EMITL2BCH4PLM",
        version="002",
        url="https://doi.org/10.5067/EMIT/EMITL2BCH4PLM.002",
        license_url=None,
        citation_text="fixture",
        retrieved_at_utc=None,
        sha256="0" * 64,
    )
    base.update(kw)
    return DataSource(**base)


def test_unknown_retrieval_time_is_null_and_explicit():
    source = _data_source()
    assert source.retrieved_at_utc is None
    dumped = source.model_dump(mode="json")
    assert "retrieved_at_utc" in dumped and dumped["retrieved_at_utc"] is None
    assert type(source).model_validate_json(source.model_dump_json()) == source


def test_retrieval_time_is_required_and_utc_when_known():
    from aether.contracts.models import DataSource

    fields = _data_source().model_dump()
    del fields["retrieved_at_utc"]
    with pytest.raises(ValidationError):
        DataSource(**fields)  # omitted is not the same as unknown
    with pytest.raises(ValidationError):
        _data_source(retrieved_at_utc=datetime(2026, 10, 17))  # naive
    aware = _data_source(retrieved_at_utc=datetime(2026, 10, 17, tzinfo=UTC))
    assert aware.retrieved_at_utc.tzinfo is not None
