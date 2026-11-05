"""Reusable analysis request and result schemas for future ML endpoints."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .region import GeographicRegion, RegionSummary


class TimeRange(BaseModel):
    """Inclusive UTC calendar date range for an analysis request."""

    model_config = ConfigDict(extra="forbid")

    start: date
    end: date

    @model_validator(mode="after")
    def validate_order(self) -> "TimeRange":
        if self.end < self.start:
            raise ValueError("end must not be before start.")
        return self


class AnalysisRequest(BaseModel):
    """Validated request envelope for a region-based analysis."""

    model_config = ConfigDict(extra="forbid")

    region: GeographicRegion
    analysis_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    indicators: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    time_range: TimeRange | None = None

    @field_validator("analysis_type")
    @classmethod
    def normalize_analysis_type(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else None

    @field_validator("indicators")
    @classmethod
    def normalize_indicators(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None

        normalized: list[str] = []

        for item in value:
            name = item.strip().lower()

            if not name:
                raise ValueError("Indicator names must not be blank.")

            if name not in normalized:
                normalized.append(name)

        return normalized


AnalysisStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
]


class AnalysisResult(BaseModel):
    """Generic analysis result envelope; domain values remain provider-supplied."""

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    analysis_id: str | None = None
    analysis_type: str | None = None
    status: AnalysisStatus
    region: RegionSummary
    results: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("analysis_id", "analysis_type", "message")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


__all__ = [
    "AnalysisRequest",
    "AnalysisResult",
    "AnalysisStatus",
    "TimeRange",
]

