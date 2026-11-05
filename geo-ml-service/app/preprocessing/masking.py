"""Raster pixel masking by geometry and numeric validity ranges."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.mask import raster_geometry_mask

from .raster import RasterInfo, RasterProcessingError, inspect_raster, validate_raster
from .vector import VectorProcessingError, geometry_to_geojson, reproject_geometry


def mask_raster(
    source_path: str | Path,
    destination_path: str | Path,
    *,
    geometry: Any | None = None,
    geometry_crs: str = "EPSG:4326",
    valid_min: float | None = None,
    valid_max: float | None = None,
    nodata: float | int | None = None,
    all_touched: bool = False,
    overwrite: bool = False,
) -> RasterInfo:
    """Write a raster with pixels outside the requested valid mask set to nodata."""
    if valid_min is not None and valid_max is not None and valid_min > valid_max:
        raise RasterProcessingError("valid_min must not be greater than valid_max.")
    if geometry is None and valid_min is None and valid_max is None:
        raise RasterProcessingError("Provide geometry, valid_min, valid_max, or a combination.")

    source = Path(source_path)
    destination = Path(destination_path)
    if destination.exists() and not overwrite:
        raise RasterProcessingError(f"Destination already exists: {destination}")
    validate_raster(source)
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with rasterio.open(source) as source_dataset:
            output_nodata = nodata if nodata is not None else source_dataset.nodata
            if output_nodata is None:
                if np.issubdtype(np.dtype(source_dataset.dtypes[0]), np.floating):
                    output_nodata = np.nan
                else:
                    raise RasterProcessingError(
                        "An integer raster needs a nodata value in the source or request."
                    )

            data = source_dataset.read()
            invalid = np.zeros((source_dataset.height, source_dataset.width), dtype=bool)
            if geometry is not None:
                if source_dataset.crs is None:
                    raise RasterProcessingError("Source raster has no coordinate reference system.")
                projected = reproject_geometry(geometry, geometry_crs, source_dataset.crs)
                geometry_mask, _ = raster_geometry_mask(
                    source_dataset,
                    [geometry_to_geojson(projected)],
                    all_touched=all_touched,
                    invert=False,
                    crop=False,
                )
                invalid |= geometry_mask

            for band_index in range(data.shape[0]):
                band = data[band_index]
                if np.issubdtype(band.dtype, np.floating):
                    invalid |= ~np.isfinite(band)
                if source_dataset.nodata is not None:
                    invalid |= band == source_dataset.nodata
                if valid_min is not None:
                    invalid |= band < valid_min
                if valid_max is not None:
                    invalid |= band > valid_max

            result = data.copy()
            result[:, invalid] = output_nodata
            profile = source_dataset.profile.copy()
            profile.update(driver="GTiff", nodata=output_nodata)
            with rasterio.open(destination, "w", **profile) as destination_dataset:
                destination_dataset.write(result)
    except VectorProcessingError as exc:
        raise RasterProcessingError(f"Invalid masking geometry: {exc}") from exc
    except (rasterio.errors.RasterioError, OSError, ValueError) as exc:
        if isinstance(exc, RasterProcessingError):
            raise
        raise RasterProcessingError(f"Raster masking failed: {source} -> {destination}") from exc

    return inspect_raster(destination)


__all__ = ["mask_raster"]

