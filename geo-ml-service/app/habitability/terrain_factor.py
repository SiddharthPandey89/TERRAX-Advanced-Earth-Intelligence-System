"""Terrain suitability factor.

Scores elevation and slope suitability from supplied terrain data (for example
DEM-derived statistics). Nothing is estimated: absent measurements are reported
as missing and invalid ones are discarded and reported.

Inputs (all optional):
    elevation_m   mean elevation above sea level, metres   weight 0.5
                  100 at <= 1000 m, 0 at >= 5000 m
    slope_deg     mean slope, degrees                       weight 0.5
                  100 at <= 5 deg, 0 at >= 35 deg

Thresholds are heuristics (see ``scoring`` module note). Landslide and flood
hazards are *not* derived here; supply them through ``risk_factor`` instead.
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

FACTOR_NAME = "terrain"

SPECS: tuple[MetricSpec, ...] = (
    MetricSpec("elevation_m", "m", 0.5, (-500.0, 9_000.0),
               lambda v: ramp_score(v, 5000.0, 1000.0)),
    MetricSpec("slope_deg", "deg", 0.5, (0.0, 90.0),
               lambda v: ramp_score(v, 35.0, 5.0)),
)

_NOTE = "Mean terrain statistics only; local relief, soil and land cover are not considered."


@dataclass(frozen=True)
class TerrainInput:
    elevation_m: float | None = None
    slope_deg: float | None = None


def evaluate_terrain(data: TerrainInput | None) -> FactorResult:
    """Evaluate terrain suitability, or report why it is unavailable."""
    if data is None:
        return unavailable_factor(
            FACTOR_NAME, "No terrain data was supplied.", missing=(s.name for s in SPECS)
        )

    components, issues = score_metrics(
        {"elevation_m": data.elevation_m, "slope_deg": data.slope_deg}, SPECS
    )
    return finalize_factor(FACTOR_NAME, components, SPECS, issues, notes=(_NOTE,))
