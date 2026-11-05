"""Raster inspection and validation primitives for geospatial preprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import rasterio
from rasterio.crs import CRS
from rasterio.errors import RasterioIOError


class RasterProcessingError(RuntimeError):
    """Raised when a raster cannot be opened or fails validation."""


@dataclass(frozen=True)
class RasterInfo:
    """Metadata describing a readable raster dataset."""

    path: str
    width: int
    height: int
    count: int
    dtypes: tuple[str, ...]
    crs: str | None
    transform: Any
    bounds: tuple[float, float, float, float]
    nodata: float | int | None


def _source_path(path: str | Path) -> Path:
    source = Path(path)
    if not source.is_file():
        raise RasterProcessingError(f"Raster file does not exist: {source}")
    return source


def inspect_raster(path: str | Path) -> RasterInfo:
    """Read raster metadata without loading pixel data into memory."""
    source = _source_path(path)
    try:
        with rasterio.open(source) as dataset:
            return RasterInfo(
                path=str(source),
                width=dataset.width,
                height=dataset.height,
                count=dataset.count,
                dtypes=tuple(dataset.dtypes),
                crs=dataset.crs.to_string() if dataset.crs else None,
                transform=dataset.transform,
                bounds=(dataset.bounds.left, dataset.bounds.bottom, dataset.bounds.right, dataset.bounds.top),
                nodata=dataset.nodata,
            )
    except (RasterioIOError, ValueError) as exc:
        raise RasterProcessingError(f"Unable to read raster metadata: {source}") from exc


def validate_raster(path: str | Path, *, require_crs: bool = True) -> RasterInfo:
    """Validate that a raster is readable, non-empty, and spatially referenced."""
    info = inspect_raster(path)
    if info.width < 1 or info.height < 1 or info.count < 1:
        raise RasterProcessingError("Raster must have positive width, height, and band count.")
    if require_crs and not info.crs:
        raise RasterProcessingError("Raster has no coordinate reference system.")
    return info


def require_target_crs(value: str | CRS) -> CRS:
    """Parse a CRS and raise a project-specific error for invalid input."""
    try:
        return CRS.from_user_input(value)
    except (TypeError, ValueError) as exc:
        raise RasterProcessingError(f"Invalid coordinate reference system: {value!r}") from exc


__all__ = ["RasterInfo", "RasterProcessingError", "inspect_raster", "require_target_crs", "validate_raster"]

