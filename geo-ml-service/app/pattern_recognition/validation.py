"""Validation and data-quality utilities shared by pattern algorithms."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np


class PatternRecognitionError(ValueError):
    """Base error for invalid or unusable pattern-recognition inputs."""


class InsufficientObservationsError(PatternRecognitionError):
    """Raised when too few valid observations remain for an algorithm."""


class PatternDependencyError(PatternRecognitionError):
    """Raised when an optional algorithm dependency is unavailable."""


@dataclass(frozen=True)
class ValidatedSeries:
    """Finite observations with their original positions and numeric time axis."""

    values: np.ndarray
    timestamps: np.ndarray
    original_indices: np.ndarray
    original_size: int

    @property
    def observed_count(self) -> int:
        return int(self.values.size)

    @property
    def missing_count(self) -> int:
        return int(self.original_size - self.observed_count)

    def as_dict(self) -> dict[str, Any]:
        return {
            "values": self.values.tolist(),
            "timestamps": self.timestamps.tolist(),
            "original_indices": self.original_indices.tolist(),
            "original_size": self.original_size,
            "observed_count": self.observed_count,
            "missing_count": self.missing_count,
        }


def validate_series(
    values: Sequence[float] | np.ndarray,
    *,
    timestamps: Sequence[Any] | np.ndarray | None = None,
    min_observations: int = 2,
    drop_missing: bool = True,
    name: str = "values",
) -> ValidatedSeries:
    """Validate a one-dimensional numeric series and safely remove missing values."""
    if isinstance(min_observations, bool) or min_observations < 1:
        raise PatternRecognitionError("min_observations must be a positive integer.")
    try:
        raw = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise PatternRecognitionError(f"{name} must contain numeric values.") from exc
    if raw.ndim != 1 or raw.size == 0:
        raise PatternRecognitionError(f"{name} must be a non-empty one-dimensional series.")
    if timestamps is None:
        time_axis = np.arange(raw.size, dtype=float)
    else:
        time_axis = _numeric_time_axis(timestamps, raw.size)
    finite = np.isfinite(raw)
    if not finite.all() and not drop_missing:
        raise PatternRecognitionError(f"{name} contains missing or non-finite values.")
    values_clean = raw[finite]
    time_clean = time_axis[finite]
    indices = np.flatnonzero(finite).astype(int)
    if values_clean.size < min_observations:
        raise InsufficientObservationsError(
            f"{name} has {values_clean.size} valid observations; at least {min_observations} are required."
        )
    if time_clean.size > 1 and not np.all(np.diff(time_clean) > 0):
        raise PatternRecognitionError("timestamps must be strictly increasing after missing values are removed.")
    return ValidatedSeries(values_clean, time_clean, indices, int(raw.size))


def validate_matrix(
    data: Sequence[Sequence[float]] | np.ndarray,
    *,
    min_observations: int = 2,
    drop_missing_rows: bool = True,
    name: str = "data",
) -> tuple[np.ndarray, np.ndarray, int]:
    """Validate a numeric feature matrix and return clean rows, indices, and original row count."""
    if isinstance(min_observations, bool) or min_observations < 1:
        raise PatternRecognitionError("min_observations must be a positive integer.")
    try:
        matrix = np.asarray(data, dtype=float)
    except (TypeError, ValueError) as exc:
        raise PatternRecognitionError(f"{name} must contain numeric features.") from exc
    if matrix.ndim == 1:
        matrix = matrix.reshape(-1, 1)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise PatternRecognitionError(f"{name} must be a non-empty one- or two-dimensional numeric array.")
    finite_rows = np.isfinite(matrix).all(axis=1)
    if not finite_rows.all() and not drop_missing_rows:
        raise PatternRecognitionError(f"{name} contains missing or non-finite rows.")
    indices = np.flatnonzero(finite_rows).astype(int)
    clean = matrix[finite_rows]
    if clean.shape[0] < min_observations:
        raise InsufficientObservationsError(
            f"{name} has {clean.shape[0]} valid rows; at least {min_observations} are required."
        )
    return clean, indices, int(matrix.shape[0])


def modified_z_scores(values: Sequence[float] | np.ndarray) -> np.ndarray:
    """Return robust absolute modified-z scores using median absolute deviation."""
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or array.size == 0 or not np.isfinite(array).all():
        raise PatternRecognitionError("modified_z_scores requires finite one-dimensional values.")
    median = float(np.median(array))
    mad = float(np.median(np.abs(array - median)))
    if mad > 0:
        return 0.6744897501960817 * np.abs(array - median) / mad
    scores = np.zeros(array.size, dtype=float)
    scores[array != median] = np.inf
    return scores


def _numeric_time_axis(timestamps: Sequence[Any] | np.ndarray, expected_size: int) -> np.ndarray:
    raw = np.asarray(timestamps)
    if raw.ndim != 1 or raw.size != expected_size:
        raise PatternRecognitionError("timestamps must be one-dimensional and match values length.")
    if np.issubdtype(raw.dtype, np.number):
        result = raw.astype(float)
    else:
        try:
            result = raw.astype("datetime64[ns]").astype("int64").astype(float) / 1_000_000_000.0
        except (TypeError, ValueError, OverflowError) as exc:
            raise PatternRecognitionError("timestamps must be numeric or parseable datetimes.") from exc
        if np.any(raw.astype("datetime64[ns]") == np.datetime64("NaT")):
            raise PatternRecognitionError("timestamps must not contain NaT.")
    if not np.isfinite(result).all():
        raise PatternRecognitionError("timestamps must be finite.")
    return result


__all__ = [
    "InsufficientObservationsError", "PatternDependencyError", "PatternRecognitionError",
    "ValidatedSeries", "modified_z_scores", "validate_matrix", "validate_series",
]

