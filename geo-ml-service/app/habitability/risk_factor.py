"""Environmental risk factor.

Converts supplied hazard indices into a *safety* score (higher = safer) so it
combines with the other factors consistently.

Inputs (all optional): normalised hazard indices produced upstream, each in
[0, 1] where 0 = no hazard and 1 = extreme hazard:

    flood      weight 0.3
    drought    weight 0.3
    wildfire   weight 0.2
    seismic    weight 0.2

Hazards are NOT derived here (no duplication of temperature or terrain logic).

Aggregation, in risk space (r = index):
    risk_index = 0.6 * max(r) + 0.4 * weighted_mean(r)
    score      = 100 * (1 - risk_index)
so one severe hazard dominates but cannot be averaged away. A hazard that was
not supplied is *unknown*, not zero: the result is flagged as potentially
understated and its confidence is reduced.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from .scoring import (
    Component,
    FactorResult,
    MetricSpec,
    finalize_factor,
    score_metrics,
    unavailable_factor,
    weighted_mean_score,
)

FACTOR_NAME = "risk"
MAX_WEIGHT = 0.6  # share of the worst hazard in the aggregate

SPECS: tuple[MetricSpec, ...] = tuple(
    MetricSpec(name, "index (0-1)", weight, (0.0, 1.0), lambda v: 100.0 * (1.0 - v))
    for name, weight in (("flood", 0.3), ("drought", 0.3), ("wildfire", 0.2), ("seismic", 0.2))
)


@dataclass(frozen=True)
class RiskInput:
    flood: float | None = None
    drought: float | None = None
    wildfire: float | None = None
    seismic: float | None = None


def _aggregate_safety(components: Sequence[Component]) -> float:
    """0.6 * worst-hazard safety + 0.4 * weighted-mean safety (equals the risk formula above)."""
    worst = min(c.score for c in components)
    return MAX_WEIGHT * worst + (1.0 - MAX_WEIGHT) * weighted_mean_score(components)


def evaluate_risk(data: RiskInput | None) -> FactorResult:
    """Evaluate environmental safety, or report why it is unavailable."""
    if data is None:
        return unavailable_factor(
            FACTOR_NAME, "No hazard data was supplied.", missing=(s.name for s in SPECS)
        )

    components, issues = score_metrics(
        {
            "flood": data.flood,
            "drought": data.drought,
            "wildfire": data.wildfire,
            "seismic": data.seismic,
        },
        SPECS,
    )
    result = finalize_factor(
        FACTOR_NAME,
        components,
        SPECS,
        issues,
        notes=("Hazard indices are used as supplied; they are not derived in this module.",),
        aggregate=_aggregate_safety,
    )
    if result.status != "available":
        return result

    notes = list(result.notes)
    if result.missing:
        notes.append("Hazards not supplied are unknown, not zero; overall risk may be understated.")
    return replace(
        result,
        notes=tuple(notes),
        details={
            "risk_index": round(1.0 - result.score / 100.0, 4),  # type: ignore[operator]
            "hazards_considered": [c.name for c in components],
        },
    )
