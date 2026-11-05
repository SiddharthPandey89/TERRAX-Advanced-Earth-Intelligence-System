"""Temporal change detection for regularly or irregularly sampled series."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from .validation import modified_z_scores, validate_series


@dataclass(frozen=True)
class ChangeEvent:
    """A detected change between two consecutive valid observations."""

    observation_index: int
    previous_observation_index: int
    delta: float
    score: float
    direction: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_index": self.observation_index,
            "previous_observation_index": self.previous_observation_index,
            "delta": self.delta,
            "score": self.score,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class ChangeDetectionResult:
    method: str
    status: str
    threshold: float
    differences: tuple[float, ...]
    events: tuple[ChangeEvent, ...]
    original_indices: tuple[int, ...]
    observed_count: int
    missing_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "status": self.status,
            "threshold": self.threshold,
            "differences": list(self.differences),
            "events": [event.as_dict() for event in self.events],
            "original_indices": list(self.original_indices),
            "observed_count": self.observed_count,
            "missing_count": self.missing_count,
        }


def detect_changes(
    values: Sequence[float] | np.ndarray,
    *,
    timestamps: Sequence[Any] | np.ndarray | None = None,
    threshold: float | None = None,
    z_threshold: float = 3.5,
    min_observations: int = 3,
) -> ChangeDetectionResult:
    """Detect unusually large consecutive changes.

    If ``threshold`` is supplied it is an absolute change threshold. Otherwise,
    robust modified z-scores of consecutive differences are used.
    """
    if threshold is not None and (not np.isfinite(threshold) or threshold < 0):
        raise ValueError("threshold must be a finite non-negative number.")
    if not np.isfinite(z_threshold) or z_threshold <= 0:
        raise ValueError("z_threshold must be a finite positive number.")
    series = validate_series(values, timestamps=timestamps, min_observations=min_observations)
    differences = np.diff(series.values)
    scores = modified_z_scores(differences) if differences.size > 1 else np.zeros(differences.size)
    if threshold is None:
        changed = scores >= z_threshold
        used_threshold = float(z_threshold)
    else:
        changed = np.abs(differences) >= threshold
        used_threshold = float(threshold)
    events = tuple(
        ChangeEvent(
            observation_index=int(series.original_indices[index + 1]),
            previous_observation_index=int(series.original_indices[index]),
            delta=float(differences[index]),
            score=float(scores[index]),
            direction="increase" if differences[index] > 0 else "decrease" if differences[index] < 0 else "unchanged",
        )
        for index in np.flatnonzero(changed)
    )
    return ChangeDetectionResult(
        method="absolute_difference" if threshold is not None else "robust_difference_modified_z_score",
        status="available",
        threshold=used_threshold,
        differences=tuple(float(value) for value in differences),
        events=events,
        original_indices=tuple(int(item) for item in series.original_indices),
        observed_count=series.observed_count,
        missing_count=series.missing_count,
    )


__all__ = ["ChangeDetectionResult", "ChangeEvent", "detect_changes"]

