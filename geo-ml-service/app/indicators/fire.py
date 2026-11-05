"""Fire occurrence statistics for explicitly classified fire-mask rasters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from .statistics import IndicatorDataError, read_valid_values


@dataclass(frozen=True)
class FireResult:
    """Observed fire-mask counts; it does not infer fire from temperature alone."""

    indicator: str
    status: str
    source: str
    total_pixel_count: int
    valid_pixel_count: int
    fire_pixel_count: int
    fire_pixel_fraction: float
    fire_values: tuple[float, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "indicator": self.indicator,
            "status": self.status,
            "source": self.source,
            "total_pixel_count": self.total_pixel_count,
            "valid_pixel_count": self.valid_pixel_count,
            "fire_pixel_count": self.fire_pixel_count,
            "fire_pixel_fraction": self.fire_pixel_fraction,
            "fire_values": list(self.fire_values),
        }


def analyze_fire_mask(
    raster_path: str | Path,
    *,
    fire_values: Iterable[float],
    band: int = 1,
) -> FireResult:
    """Count pixels matching codes from a documented fire classification product."""
    values_to_count = tuple(float(value) for value in fire_values)
    if not values_to_count:
        raise ValueError("fire_values must contain at least one class value.")
    if not all(np.isfinite(value) for value in values_to_count):
        raise ValueError("fire_values must contain only finite numbers.")

    values, total_pixels, _ = read_valid_values(raster_path, band=band)
    valid_count = int(values.size)
    if valid_count == 0:
        raise IndicatorDataError(f"Dataset {raster_path!s} contains no valid fire-mask pixels.")
    fire_count = int(np.isin(values, values_to_count).sum())

    return FireResult(
        indicator="fire",
        status="available",
        source=str(Path(raster_path)),
        total_pixel_count=total_pixels,
        valid_pixel_count=valid_count,
        fire_pixel_count=fire_count,
        fire_pixel_fraction=fire_count / valid_count if valid_count else 0.0,
        fire_values=values_to_count,
    )


__all__ = ["FireResult", "analyze_fire_mask"]

