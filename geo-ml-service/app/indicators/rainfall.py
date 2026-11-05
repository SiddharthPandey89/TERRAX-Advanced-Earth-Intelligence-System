"""Rainfall statistics from a documented precipitation raster band."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .statistics import RasterIndicatorResult, analyze_single_band

RainfallUnit = Literal["millimetres", "metres"]


def analyze_rainfall(
    raster_path: str | Path,
    *,
    source_unit: RainfallUnit,
    band: int = 1,
) -> RasterIndicatorResult:
    """Calculate non-negative rainfall statistics in millimetres."""
    if source_unit not in ("millimetres", "metres"):
        raise ValueError("source_unit must be 'millimetres' or 'metres'.")
    transform = (lambda values: values * 1000.0) if source_unit == "metres" else None
    return analyze_single_band(
        raster_path,
        indicator="rainfall",
        unit="mm",
        band=band,
        value_transform=transform,
        valid_range=(0.0, None),
        notes=(f"Input raster unit: {source_unit}.",),
    )


__all__ = ["RainfallUnit", "analyze_rainfall"]

