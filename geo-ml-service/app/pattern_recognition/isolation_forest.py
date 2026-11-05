"""Multivariate anomaly detection using scikit-learn Isolation Forest."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from .validation import PatternDependencyError, validate_matrix


@dataclass(frozen=True)
class IsolationForestResult:
    method: str
    status: str
    contamination: str | float
    feature_names: tuple[str, ...]
    labels: tuple[int, ...]
    anomaly_scores: tuple[float, ...]
    original_indices: tuple[int, ...]
    observed_count: int
    missing_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "status": self.status,
            "contamination": self.contamination,
            "feature_names": list(self.feature_names),
            "labels": list(self.labels),
            "anomaly_scores": list(self.anomaly_scores),
            "original_indices": list(self.original_indices),
            "observed_count": self.observed_count,
            "missing_count": self.missing_count,
        }


def detect_isolation_forest(
    data: Sequence[Sequence[float]] | np.ndarray,
    *,
    contamination: str | float = "auto",
    n_estimators: int = 100,
    max_samples: str | int | float = "auto",
    random_state: int | None = 42,
    feature_names: Sequence[str] | None = None,
    min_observations: int = 10,
) -> IsolationForestResult:
    """Fit Isolation Forest and return labels (-1 anomaly, 1 normal).

    Missing rows are excluded rather than imputed. ``anomaly_scores`` are the
    negated scikit-learn decision function, so larger values are more unusual;
    they are not probabilities.
    """
    if isinstance(n_estimators, bool) or n_estimators < 10:
        raise ValueError("n_estimators must be at least 10.")
    matrix, indices, original_size = validate_matrix(data, min_observations=min_observations)
    if feature_names is None:
        names = tuple(f"feature_{index + 1}" for index in range(matrix.shape[1]))
    else:
        names = tuple(str(name).strip() for name in feature_names)
        if len(names) != matrix.shape[1] or any(not name for name in names):
            raise ValueError("feature_names must match the number of columns and contain no blanks.")
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError as exc:
        raise PatternDependencyError(
            "Isolation Forest requires scikit-learn; install a compatible scikit-learn release."
        ) from exc
    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        max_samples=max_samples,
        random_state=random_state,
    )
    labels = model.fit_predict(matrix)
    scores = -model.decision_function(matrix)
    return IsolationForestResult(
        method="sklearn_isolation_forest",
        status="available",
        contamination=contamination,
        feature_names=names,
        labels=tuple(int(label) for label in labels),
        anomaly_scores=tuple(float(score) for score in scores),
        original_indices=tuple(int(index) for index in indices),
        observed_count=int(matrix.shape[0]),
        missing_count=int(original_size - matrix.shape[0]),
    )


__all__ = ["IsolationForestResult", "detect_isolation_forest"]

