"""Elevation statistics from a documented digital elevation model raster."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .statistics import RasterIndicatorResult, analyze_single_band

ElevationUnit = Literal["metres", "feet"]


def analyze_elevation(
    raster_path: str | Path,
    *,
    source_unit: ElevationUnit,
    band: int = 1,
) -> RasterIndicatorResult:
    """Calculate elevation statistics in metres."""
    if source_unit not in ("metres", "feet"):
        raise ValueError("source_unit must be 'metres' or 'feet'.")
    transform = (lambda values: values * 0.3048) if source_unit == "feet" else None
    return analyze_single_band(
        raster_path,
        indicator="elevation",
        unit="m",
        band=band,
        value_transform=transform,
        notes=(f"Input raster unit: {source_unit}.",),
    )


__all__ = ["ElevationUnit", "analyze_elevation"]

