"""Robust univariate anomaly detection using modified z-scores."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from .validation import modified_z_scores, validate_series


@dataclass(frozen=True)
class AnomalyResult:
    """Observed anomaly scores for valid input positions only."""

    method: str
    status: str
    threshold: float
    values: tuple[float, ...]
    scores: tuple[float, ...]
    anomaly_mask: tuple[bool, ...]
    original_indices: tuple[int, ...]
    observed_count: int
    missing_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "status": self.status,
            "threshold": self.threshold,
            "values": list(self.values),
            "scores": list(self.scores),
            "anomaly_mask": list(self.anomaly_mask),
            "original_indices": list(self.original_indices),
            "observed_count": self.observed_count,
            "missing_count": self.missing_count,
        }


def detect_anomalies(
    values: Sequence[float] | np.ndarray,
    *,
    threshold: float = 3.5,
    timestamps: Sequence[Any] | np.ndarray | None = None,
    min_observations: int = 3,
) -> AnomalyResult:
    """Detect univariate outliers with a median/MAD-based modified z-score.

    Missing values are excluded and reported through ``missing_count``; they are
    never imputed or classified as anomalies.
    """
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("threshold must be a finite positive number.")
    series = validate_series(values, timestamps=timestamps, min_observations=min_observations)
    scores = modified_z_scores(series.values)
    mask = scores >= threshold
    return AnomalyResult(
        method="modified_z_score_median_mad",
        status="available",
        threshold=float(threshold),
        values=tuple(float(value) for value in series.values),
        scores=tuple(float(score) for score in scores),
        anomaly_mask=tuple(bool(item) for item in mask),
        original_indices=tuple(int(item) for item in series.original_indices),
        observed_count=series.observed_count,
        missing_count=series.missing_count,
    )


__all__ = ["AnomalyResult", "detect_anomalies"]

