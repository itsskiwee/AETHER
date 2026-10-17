"""Keyed random streams (PRD 8.2 step 5, FR-SIM-002).

Never call ``np.random.default_rng()`` without a key from here, and never use the global
``np.random`` state. Each draw site gets its own stream derived from (seed, namespace, *key), so:

- runs are bit-reproducible;
- two policies that observe the same source with the same sensor in the same minute get the same
  uniform draws (common random numbers), while different decisions still yield different
  observations.

Every stream derives from the single run seed (``ScenarioConfig.random_seed``). There are no
per-subsystem seeds in config, so changing the run seed changes truth, weather and outcomes
together, and two policies run with the same seed see identical truth and weather.

Reserved namespaces (add new ones to this list in the same PR that uses them):
    "truth"     (source_id,)                         hidden regime, flux and on/off history
    "outcome"   (source_id, spacecraft_id, sensor_id, minute_bucket_iso)
                                                     validity, detection, flux error, FP flux draws
    "weather"   ("cloud" | "wind" | "forecast" | "wind_analysis", ...)  synthetic weather fields
    "placement" ()                                   synthetic source locations
    "requests"  ()                                   Poisson request stream for first_feasible (B1)
    "solver"    (policy_id, plan_revision)           CP-SAT random_seed via derive_seed()
    "reference" (policy_id,)                         random_feasible reference policy
"""

from __future__ import annotations

import hashlib
from datetime import datetime

import numpy as np

RESERVED_NAMESPACES = frozenset(
    {"truth", "outcome", "weather", "placement", "requests", "solver", "reference"}
)


def stream_key(seed: int, namespace: str, *key: str | int) -> str:
    if namespace not in RESERVED_NAMESPACES:
        raise ValueError(f"unregistered RNG namespace {namespace!r}")
    return "|".join([str(seed), namespace, *map(str, key)])


def keyed_rng(seed: int, namespace: str, *key: str | int) -> np.random.Generator:
    digest = hashlib.blake2b(stream_key(seed, namespace, *key).encode(), digest_size=16).digest()
    return np.random.default_rng(np.random.SeedSequence(int.from_bytes(digest, "little")))


def minute_bucket(t: datetime) -> str:
    """Bucket used in ``outcome`` keys so near-identical acquisition times share draws."""
    return t.replace(second=0, microsecond=0).isoformat()


def derive_seed(seed: int, namespace: str, *key: str | int) -> int:
    """Non-negative 31-bit integer seed for libraries that take an int (e.g. CP-SAT)."""
    digest = hashlib.blake2b(stream_key(seed, namespace, *key).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "little") % (2**31 - 1)
