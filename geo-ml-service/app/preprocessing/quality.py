"""Quality checks for raster readability, spatial reference, and valid pixels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from .raster import RasterProcessingError, validate_raster


@dataclass(frozen=True)
class RasterQualityReport:
    """Measured raster quality facts and a conservative validity result."""

    path: str
    width: int
    height: int
    band_count: int
    crs: str | None
    total_pixels: int
    valid_pixels: int
    valid_pixel_fraction: float
    issues: tuple[str, ...]
    is_valid: bool


def assess_raster_quality(
    path: str | Path,
    *,
    window_size: int = 1024,
    require_crs: bool = True,
) -> RasterQualityReport:
    """Assess raster validity without loading the entire dataset at once."""
    if window_size < 1:
        raise RasterProcessingError("window_size must be a positive integer.")
    info = validate_raster(path, require_crs=False)
    issues: list[str] = []
    if require_crs and not info.crs:
        issues.append("missing coordinate reference system")

    valid_pixels = 0
    total_pixels = info.width * info.height
    try:
        with rasterio.open(path) as dataset:
            for row in range(0, dataset.height, window_size):
                for column in range(0, dataset.width, window_size):
                    height = min(window_size, dataset.height - row)
                    width = min(window_size, dataset.width - column)
                    window = Window(column, row, width, height)
                    values = dataset.read(window=window, masked=False)
                    valid = np.ones((height, width), dtype=bool)
                    for band in values:
                        if np.issubdtype(band.dtype, np.floating):
                            valid &= np.isfinite(band)
                        if dataset.nodata is not None:
                            valid &= band != dataset.nodata
                    valid_pixels += int(valid.sum())
    except (rasterio.errors.RasterioError, OSError, ValueError) as exc:
        raise RasterProcessingError(f"Unable to assess raster quality: {path}") from exc

    if valid_pixels == 0:
        issues.append("raster contains no valid pixels")
    fraction = valid_pixels / total_pixels if total_pixels else 0.0
    return RasterQualityReport(
        path=info.path,
        width=info.width,
        height=info.height,
        band_count=info.count,
        crs=info.crs,
        total_pixels=total_pixels,
        valid_pixels=valid_pixels,
        valid_pixel_fraction=fraction,
        issues=tuple(issues),
        is_valid=not issues,
    )


__all__ = ["RasterQualityReport", "assess_raster_quality"]

