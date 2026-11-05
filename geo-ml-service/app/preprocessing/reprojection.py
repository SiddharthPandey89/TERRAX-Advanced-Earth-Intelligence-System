"""Raster reprojection using Rasterio and GDAL-supported coordinate systems."""

from __future__ import annotations

from pathlib import Path

import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject

from .raster import RasterInfo, RasterProcessingError, inspect_raster, require_target_crs, validate_raster


def _resampling(value: Resampling | str) -> Resampling:
    if isinstance(value, Resampling):
        return value
    try:
        return Resampling[value.lower()]
    except (KeyError, AttributeError) as exc:
        valid = ", ".join(member.name for member in Resampling)
        raise RasterProcessingError(f"Unsupported resampling method; choose one of: {valid}.") from exc


def reproject_raster(
    source_path: str | Path,
    destination_path: str | Path,
    target_crs: str,
    *,
    resampling: Resampling | str = Resampling.nearest,
    overwrite: bool = False,
) -> RasterInfo:
    """Reproject every band of a raster and write a new GeoTIFF."""
    source = Path(source_path)
    destination = Path(destination_path)
    if destination.exists() and not overwrite:
        raise RasterProcessingError(f"Destination already exists: {destination}")
    source_info = validate_raster(source)
    target = require_target_crs(target_crs)
    method = _resampling(resampling)
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with rasterio.open(source) as source_dataset:
            transform, width, height = calculate_default_transform(
                source_dataset.crs,
                target,
                source_dataset.width,
                source_dataset.height,
                *source_dataset.bounds,
            )
            profile = source_dataset.profile.copy()
            profile.update(
                crs=target,
                transform=transform,
                width=width,
                height=height,
                driver="GTiff",
            )
            if not profile.get("tiled", False):
                profile.pop("blockxsize", None)
                profile.pop("blockysize", None)
            with rasterio.open(destination, "w", **profile) as destination_dataset:
                for band_index in range(1, source_dataset.count + 1):
                    reproject(
                        source=rasterio.band(source_dataset, band_index),
                        destination=rasterio.band(destination_dataset, band_index),
                        src_transform=source_dataset.transform,
                        src_crs=source_dataset.crs,
                        dst_transform=transform,
                        dst_crs=target,
                        resampling=method,
                        src_nodata=source_dataset.nodata,
                        dst_nodata=source_dataset.nodata,
                    )
    except (rasterio.errors.RasterioError, ValueError, OSError) as exc:
        raise RasterProcessingError(f"Raster reprojection failed: {source} -> {destination}") from exc

    result = inspect_raster(destination)
    if result.crs is None:
        raise RasterProcessingError("Reprojected raster has no coordinate reference system.")
    if source_info.count != result.count:
        raise RasterProcessingError("Reprojection changed the raster band count unexpectedly.")
    return result


__all__ = ["reproject_raster"]
