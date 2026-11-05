"""Water measurement statistics from an explicitly identified raster dataset."""

from __future__ import annotations

from pathlib import Path

from .statistics import RasterIndicatorResult, analyze_single_band


def analyze_water(
    raster_path: str | Path,
    *,
    unit: str,
    band: int = 1,
    non_negative: bool = True,
) -> RasterIndicatorResult:
    """Calculate statistics for a water measurement raster.

    The function does not infer water availability from unrelated measurements;
    the caller must supply a dataset whose values and unit are documented.
    """
    if not unit.strip():
        raise ValueError("unit must be a non-empty string.")
    return analyze_single_band(
        raster_path,
        indicator="water",
        unit=unit.strip(),
        band=band,
        valid_range=(0.0, None) if non_negative else None,
    )


__all__ = ["analyze_water"]

