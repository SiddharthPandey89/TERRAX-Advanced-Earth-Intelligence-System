"""Temperature indicator calculations from a documented raster band."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .statistics import RasterIndicatorResult, analyze_single_band

TemperatureUnit = Literal["celsius", "kelvin"]


def analyze_temperature(
    raster_path: str | Path,
    *,
    source_unit: TemperatureUnit,
    band: int = 1,
) -> RasterIndicatorResult:
    """Calculate temperature statistics, returning output in degrees Celsius."""
    if source_unit not in ("celsius", "kelvin"):
        raise ValueError("source_unit must be 'celsius' or 'kelvin'.")
    transform = (lambda values: values - 273.15) if source_unit == "kelvin" else None
    return analyze_single_band(
        raster_path,
        indicator="temperature",
        unit="°C",
        band=band,
        value_transform=transform,
        notes=(f"Input raster unit: {source_unit}.",),
    )


__all__ = ["TemperatureUnit", "analyze_temperature"]

