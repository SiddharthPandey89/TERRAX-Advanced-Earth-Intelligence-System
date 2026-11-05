"""Deterministic linear trend analysis for environmental time series."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from .validation import validate_series


@dataclass(frozen=True)
class TrendResult:
    method: str
    status: str
    slope: float
    intercept: float
    r_squared: float
    residual_standard_deviation: float
    direction: str
    time_origin: float
    original_indices: tuple[int, ...]
    observed_count: int
    missing_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "status": self.status,
            "slope": self.slope,
            "intercept": self.intercept,
            "r_squared": self.r_squared,
            "residual_standard_deviation": self.residual_standard_deviation,
            "direction": self.direction,
            "time_origin": self.time_origin,
            "original_indices": list(self.original_indices),
            "observed_count": self.observed_count,
            "missing_count": self.missing_count,
        }


def analyze_trend(
    values: Sequence[float] | np.ndarray,
    *,
    timestamps: Sequence[Any] | np.ndarray | None = None,
    min_observations: int = 3,
) -> TrendResult:
    """Fit a least-squares line; slope is measured per timestamp unit."""
    series = validate_series(values, timestamps=timestamps, min_observations=min_observations)
    x = series.timestamps - series.timestamps[0]
    y = series.values
    if np.allclose(x, 0):
        raise ValueError("timestamps must contain at least two distinct values.")
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    residuals = y - fitted
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared = 1.0 if ss_tot == 0 and ss_res == 0 else 1.0 - ss_res / ss_tot if ss_tot else 0.0
    direction = "increasing" if slope > 0 else "decreasing" if slope < 0 else "stable"
    return TrendResult(
        method="ordinary_least_squares",
        status="available",
        slope=float(slope),
        intercept=float(intercept),
        r_squared=float(max(0.0, min(1.0, r_squared))),
        residual_standard_deviation=float(np.std(residuals, ddof=0)),
        direction=direction,
        time_origin=float(series.timestamps[0]),
        original_indices=tuple(int(index) for index in series.original_indices),
        observed_count=series.observed_count,
        missing_count=series.missing_count,
    )


__all__ = ["TrendResult", "analyze_trend"]

