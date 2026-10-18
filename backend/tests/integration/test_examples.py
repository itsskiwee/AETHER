import json
from pathlib import Path

from aether.contracts.models import RunRecord

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "docs" / "examples"


def test_policy_examples_reload_and_cover_interaction_states():
    paths = [EXAMPLES / "run.json", EXAMPLES / "run_largest_first.json"]
    records = [RunRecord.model_validate_json(path.read_text(encoding="utf-8")) for path in paths]
    assert len({record.policy_id for record in records}) == 2
    for record in records:
        assert len(record.plans) == 3
        assert len(record.acquisitions) == 6
        assert len(record.validations) == len(record.plans)
        assert {item.outcome.value for item in record.acquisitions} == {
            "DETECTION",
            "VALID_NON_DETECTION",
            "INVALID_ACQUISITION",
            "NOT_OBSERVED",
        }
        assert any(event.payload.get("cause") == "forecast_revision" for event in record.events)
        # The public computed selection list survives JSON serialization.
        raw = json.loads(paths[records.index(record)].read_text(encoding="utf-8"))
        assert all("selected_window_ids" in plan for plan in raw["plans"])
