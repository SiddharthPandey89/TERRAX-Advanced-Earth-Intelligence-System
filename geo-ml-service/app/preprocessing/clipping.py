"""Geometry-based raster clipping and cropping."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import rasterio
from rasterio.mask import mask

from .raster import RasterInfo, RasterProcessingError, inspect_raster, validate_raster
from .vector import VectorProcessingError, geometry_to_geojson, reproject_geometry


def clip_raster(
    source_path: str | Path,
    destination_path: str | Path,
    geometry: Any,
    *,
    geometry_crs: str = "EPSG:4326",
    crop: bool = True,
    all_touched: bool = False,
    nodata: float | int | None = None,
    overwrite: bool = False,
) -> RasterInfo:
    """Clip a raster to a validated GeoJSON or Shapely geometry."""
    source = Path(source_path)
    destination = Path(destination_path)
    if destination.exists() and not overwrite:
        raise RasterProcessingError(f"Destination already exists: {destination}")
    validate_raster(source)
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with rasterio.open(source) as source_dataset:
            if source_dataset.crs is None:
                raise RasterProcessingError("Source raster has no coordinate reference system.")
            clipped_geometry = reproject_geometry(geometry, geometry_crs, source_dataset.crs)
            data, transform = mask(
                source_dataset,
                [geometry_to_geojson(clipped_geometry)],
                crop=crop,
                all_touched=all_touched,
                nodata=nodata if nodata is not None else source_dataset.nodata,
            )
            profile = source_dataset.profile.copy()
            profile.update(
                driver="GTiff",
                height=data.shape[1],
                width=data.shape[2],
                transform=transform,
                nodata=nodata if nodata is not None else source_dataset.nodata,
            )
            with rasterio.open(destination, "w", **profile) as destination_dataset:
                destination_dataset.write(data)
    except VectorProcessingError as exc:
        raise RasterProcessingError(f"Invalid clipping geometry: {exc}") from exc
    except ValueError as exc:
        raise RasterProcessingError("Clipping geometry does not overlap the raster.") from exc
    except (rasterio.errors.RasterioError, OSError) as exc:
        raise RasterProcessingError(f"Raster clipping failed: {source} -> {destination}") from exc

    return inspect_raster(destination)


__all__ = ["clip_raster"]

