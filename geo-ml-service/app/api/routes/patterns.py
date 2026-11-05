"""Validated time-series pattern-recognition endpoints."""
from __future__ import annotations

import math
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.pattern_recognition.anomaly import detect_anomalies
from app.pattern_recognition.change_detection import detect_changes
from app.pattern_recognition.ewma import monitor_ewma
from app.pattern_recognition.isolation_forest import detect_isolation_forest
from app.pattern_recognition.trend import analyze_trend

router = APIRouter(prefix="/patterns", tags=["pattern recognition"])

class PatternRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["anomaly", "trend", "change", "ewma", "isolation_forest"]
    values: list[float | None] = Field(min_length=3, max_length=50000)
    timestamps: list[str | float | int | None] | None = Field(default=None, max_length=50000)
    source: str = Field(min_length=1, max_length=300)
    unit: str = Field(min_length=1, max_length=64)
    threshold: float | None = Field(default=None, gt=0, le=1000)
    feature_names: list[str] | None = Field(default=None, max_length=100)

    @field_validator("source", "unit")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip(): raise ValueError("Value must not be blank.")
        return value.strip()

    @field_validator("values")
    @classmethod
    def finite_values(cls, values: list[float | None]) -> list[float | None]:
        if sum(v is not None for v in values) < 3: raise ValueError("At least three non-null observations are required.")
        if any(v is not None and not math.isfinite(v) for v in values): raise ValueError("All observations must be finite numbers or null.")
        return values

@router.post("/analyze")
async def analyze_patterns(payload: PatternRequest) -> dict[str, Any]:
    if payload.timestamps is not None and len(payload.timestamps) != len(payload.values):
        raise HTTPException(422, "timestamps and values must have equal lengths.")
    try:
        common = {"timestamps": payload.timestamps} if payload.timestamps is not None else {}
        if payload.method == "trend": result = analyze_trend(payload.values, **common).as_dict()
        elif payload.method == "anomaly": result = detect_anomalies(payload.values, threshold=payload.threshold or 3.5, **common).as_dict()
        elif payload.method == "change": result = detect_changes(payload.values, z_threshold=payload.threshold or 3.5, **common).as_dict()
        elif payload.method == "ewma": result = monitor_ewma(payload.values, **common).as_dict()
        else:
            if any(row is None for row in payload.values): raise ValueError("Isolation Forest requires complete univariate rows; missing values are not imputed.")
            rows = [[v] for v in payload.values]
            result = detect_isolation_forest(rows, feature_names=payload.feature_names or [payload.unit]).as_dict()
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)[:300]) from exc
    return {"success": True, "method": payload.method, "source": payload.source, "unit": payload.unit,
            "classification": "derived_model_output_from_caller_supplied_series",
            "measurement_note": "This endpoint analyzes supplied observations; it does not fetch or verify environmental measurements.",
            "result": result}
