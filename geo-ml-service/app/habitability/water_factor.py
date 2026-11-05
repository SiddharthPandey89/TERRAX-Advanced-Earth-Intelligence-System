"""Water availability factor.

Scores water access from supplied water measurements. Nothing is estimated:
absent measurements are reported as missing and invalid ones are discarded and
reported.

Inputs (all optional):
    availability_index             0-1, higher = more water available   weight 0.5
                                   (normalised upstream; score = index * 100)
    groundwater_depth_m            depth to water table, metres         weight 0.3
                                   100 at <= 10 m, 0 at >= 150 m
    distance_to_surface_water_km   nearest river/lake/coast, km         weight 0.2
                                   100 at <= 1 km, 0 at >= 50 km

Thresholds are heuristics (see ``scoring`` module note). Water quality and
seasonal variability are not considered.
"""

from __future__ import annotations

from dataclasses import dataclass

from .scoring import (
    FactorResult,
    MetricSpec,
    finalize_factor,
    ramp_score,
    score_metrics,
    unavailable_factor,
)

FACTOR_NAME = "water"

SPECS: tuple[MetricSpec, ...] = (
    MetricSpec("availability_index", "index (0-1)", 0.5, (0.0, 1.0),
               lambda v: v * 100.0),
    MetricSpec("groundwater_depth_m", "m", 0.3, (0.0, 10_000.0),
               lambda v: ramp_score(v, 150.0, 10.0)),
    MetricSpec("distance_to_surface_water_km", "km", 0.2, (0.0, 20_000.0),
               lambda v: ramp_score(v, 50.0, 1.0)),
)

_NOTE = "Water quality and seasonal variability are not considered."


@dataclass(frozen=True)
class WaterInput:
    availability_index: float | None = None
    groundwater_depth_m: float | None = None
    distance_to_surface_water_km: float | None = None


def evaluate_water(data: WaterInput | None) -> FactorResult:
    """Evaluate water availability, or report why it is unavailable."""
    if data is None:
        return unavailable_factor(
            FACTOR_NAME, "No water data was supplied.", missing=(s.name for s in SPECS)
        )

    components, issues = score_metrics(
        {
            "availability_index": data.availability_index,
            "groundwater_depth_m": data.groundwater_depth_m,
            "distance_to_surface_water_km": data.distance_to_surface_water_km,
        },
        SPECS,
    )
    return finalize_factor(FACTOR_NAME, components, SPECS, issues, notes=(_NOTE,))
