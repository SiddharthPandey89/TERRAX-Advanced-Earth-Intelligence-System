"""Vegetation and NDVI calculations from real spectral raster datasets."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio

from .statistics import (
    IndicatorDataError,
    RasterIndicatorResult,
    analyze_single_band,
    statistics_from_values,
)


def analyze_ndvi(
    raster_path: str | Path,
    *,
    band: int = 1,
) -> RasterIndicatorResult:
    """Calculate statistics for a raster already representing NDVI values."""
    return analyze_single_band(
        raster_path,
        indicator="ndvi",
        unit="unitless",
        band=band,
        valid_range=(-1.0, 1.0),
        notes=("Values outside the physical NDVI range were excluded.",),
    )


def calculate_ndvi(
    red_raster_path: str | Path,
    nir_raster_path: str | Path,
    *,
    red_band: int = 1,
    nir_band: int = 1,
) -> RasterIndicatorResult:
    """Calculate NDVI from aligned red and near-infrared raster bands."""
    red_path = Path(red_raster_path)
    nir_path = Path(nir_raster_path)

    try:
        with rasterio.open(red_path) as red_dataset, rasterio.open(nir_path) as nir_dataset:
            if (red_dataset.width, red_dataset.height) != (
                nir_dataset.width,
                nir_dataset.height,
            ):
                raise IndicatorDataError("Red and NIR rasters must have identical dimensions.")
            if red_dataset.crs != nir_dataset.crs or red_dataset.transform != nir_dataset.transform:
                raise IndicatorDataError("Red and NIR rasters must share CRS and transform.")
            if not 1 <= red_band <= red_dataset.count or not 1 <= nir_band <= nir_dataset.count:
                raise IndicatorDataError("Requested NDVI band does not exist.")

            red = np.ma.asarray(red_dataset.read(red_band, masked=True), dtype=float)
            nir = np.ma.asarray(nir_dataset.read(nir_band, masked=True), dtype=float)
            combined_mask = np.ma.getmaskarray(red) | np.ma.getmaskarray(nir)
            red_values = np.asarray(red.filled(np.nan), dtype=float)
            nir_values = np.asarray(nir.filled(np.nan), dtype=float)
            denominator = nir_values + red_values
            valid = (
                ~combined_mask
                & np.isfinite(red_values)
                & np.isfinite(nir_values)
                & np.isfinite(denominator)
                & (denominator != 0)
            )
            ndvi = (nir_values - red_values) / denominator
            valid &= ndvi >= -1.0
            valid &= ndvi <= 1.0
            values = ndvi[valid]
            total_pixels = red_dataset.width * red_dataset.height
    except IndicatorDataError:
        raise
    except (rasterio.errors.RasterioError, OSError, ValueError) as exc:
        raise IndicatorDataError("Unable to read the red and NIR rasters for NDVI.") from exc

    source = f"red={red_path};nir={nir_path}"
    statistics = statistics_from_values(
        values,
        total_pixel_count=total_pixels,
        indicator="ndvi",
        unit="unitless",
        source=source,
    )
    return RasterIndicatorResult(
        indicator="ndvi",
        status="available",
        unit="unitless",
        source=source,
        statistics=statistics,
        notes=(
            "NDVI=(NIR-red)/(NIR+red); zero denominators and values outside [-1, 1] were excluded.",
        ),
    )


__all__ = ["analyze_ndvi", "calculate_ndvi"]

