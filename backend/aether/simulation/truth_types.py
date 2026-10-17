"""Hidden ground-truth container.

RESTRICTED: import only from aether.simulation and aether.evaluation.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
from pydantic import BaseModel, ConfigDict

from aether.contracts.enums import ProvenanceClass, Regime


class SourceTruth(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    source_id: str
    regime: Regime
    median_flux_kg_h: float
    active: np.ndarray  # bool[hours], index h covers [t0 + h, t0 + h + 1)
    flux_kg_h: np.ndarray  # float[hours], 0 where inactive


class TruthHistory(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    provenance_class: ProvenanceClass = ProvenanceClass.SIMULATED_GROUND_TRUTH
    epoch_utc: datetime
    hours: int
    sources: dict[str, SourceTruth]

    def hour_index(self, t_utc: datetime) -> int:
        idx = int((t_utc - self.epoch_utc).total_seconds() // 3600)
        if not 0 <= idx < self.hours:
            raise IndexError(f"{t_utc} outside truth horizon")
        return idx

    def emitted_mass_t(self, source_id: str) -> float:
        """True emitted mass over the horizon in tonnes CH4 (PR-E02)."""
        return float(self.sources[source_id].flux_kg_h.sum()) / 1000.0
