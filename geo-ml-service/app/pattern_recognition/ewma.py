"""Exponentially weighted moving-average monitoring."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from .validation import validate_series


@dataclass(frozen=True)
class EWMAResult:
    method: str
    status: str
    alpha: float
    sigma_multiplier: float
    ewma: tuple[float, ...]
    center: float
    lower_control_limit: float | None
    upper_control_limit: float | None
    signal_mask: tuple[bool, ...]
    original_indices: tuple[int, ...]
    observed_count: int
    missing_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "status": self.status,
            "alpha": self.alpha,
            "sigma_multiplier": self.sigma_multiplier,
            "ewma": list(self.ewma),
            "center": self.center,
            "lower_control_limit": self.lower_control_limit,
            "upper_control_limit": self.upper_control_limit,
            "signal_mask": list(self.signal_mask),
            "original_indices": list(self.original_indices),
            "observed_count": self.observed_count,
            "missing_count": self.missing_count,
        }


def monitor_ewma(
    values: Sequence[float] | np.ndarray,
    *,
    alpha: float = 0.3,
    sigma_multiplier: float = 3.0,
    timestamps: Sequence[Any] | np.ndarray | None = None,
    min_observations: int = 3,
) -> EWMAResult:
    """Calculate EWMA and flag values outside data-derived control limits.

    The center and standard deviation are estimated from the supplied valid
    observations. A zero-variance series yields no control-limit signals.
    """
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be greater than 0 and at most 1.")
    if not np.isfinite(sigma_multiplier) or sigma_multiplier <= 0:
        raise ValueError("sigma_multiplier must be a finite positive number.")
    series = validate_series(values, timestamps=timestamps, min_observations=min_observations)
    observations = series.values
    center = float(np.mean(observations))
    sigma = float(np.std(observations, ddof=1)) if observations.size > 1 else 0.0
    ewma = np.empty(observations.size, dtype=float)
    ewma[0] = observations[0]
    for index in range(1, observations.size):
        ewma[index] = alpha * observations[index] + (1.0 - alpha) * ewma[index - 1]
    if sigma == 0:
        lower = upper = None
        signal = np.zeros(observations.size, dtype=bool)
    else:
        spread = sigma_multiplier * sigma * np.sqrt(alpha / (2.0 - alpha))
        lower, upper = center - spread, center + spread
        signal = (ewma < lower) | (ewma > upper)
    return EWMAResult(
        method="ewma_control_limits",
        status="available",
        alpha=float(alpha),
        sigma_multiplier=float(sigma_multiplier),
        ewma=tuple(float(value) for value in ewma),
        center=center,
        lower_control_limit=None if lower is None else float(lower),
        upper_control_limit=None if upper is None else float(upper),
        signal_mask=tuple(bool(item) for item in signal),
        original_indices=tuple(int(item) for item in series.original_indices),
        observed_count=series.observed_count,
        missing_count=series.missing_count,
    )


__all__ = ["EWMAResult", "monitor_ewma"]

