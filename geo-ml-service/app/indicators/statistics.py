"""Shared raster statistics and indicator result primitives."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import rasterio

from ..preprocessing.raster import RasterProcessingError, validate_raster


class IndicatorDataError(RasterProcessingError):
    """Raised when an indicator dataset cannot produce a valid measurement."""


@dataclass(frozen=True)
class RasterStatistics:
    """Descriptive statistics for valid pixels from one raster band."""

    indicator: str
    source: str
    unit: str
    total_pixel_count: int
    valid_pixel_count: int
    nodata_pixel_count: int
    mean: float
    minimum: float
    maximum: float
    standard_deviation: float

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass(frozen=True)
class RasterIndicatorResult:
    """Successful result backed by a real raster dataset."""

    indicator: str
    status: str
    unit: str
    source: str
    statistics: RasterStatistics
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "indicator": self.indicator,
            "status": self.status,
            "unit": self.unit,
            "source": self.source,
            "statistics": self.statistics.as_dict(),
            "notes": list(self.notes),
        }


def read_valid_values(
    raster_path: str | Path,
    *,
    band: int = 1,
    value_transform: Callable[[np.ma.MaskedArray], np.ma.MaskedArray] | None = None,
    valid_range: tuple[float | None, float | None] | None = None,
) -> tuple[np.ndarray, int, float | int | None]:
    """Read one band and return finite, non-NoData values and pixel totals."""
    try:
        source = Path(raster_path)
        info = validate_raster(source)
        if not 1 <= band <= info.count:
            raise IndicatorDataError(f"Band must be between 1 and {info.count}; received {band}.")
        with rasterio.open(source) as dataset:
            values = np.ma.asarray(dataset.read(band, masked=True), dtype=float)
            if value_transform is not None:
                values = np.ma.asarray(value_transform(values), dtype=float)
            values = np.ma.masked_where(~np.isfinite(values), values)

            if valid_range is not None:
                lower, upper = valid_range
                if lower is not None:
                    values = np.ma.masked_less(values, lower)
                if upper is not None:
                    values = np.ma.masked_greater(values, upper)

            valid = np.asarray(values.compressed(), dtype=float)
            return valid, dataset.width * dataset.height, dataset.nodata
    except IndicatorDataError:
        raise
    except (RasterProcessingError, rasterio.errors.RasterioError, OSError, ValueError) as exc:
        raise IndicatorDataError(f"Unable to read indicator raster: {source}") from exc


def statistics_from_values(
    values: np.ndarray,
    *,
    total_pixel_count: int,
    indicator: str,
    unit: str,
    source: str,
) -> RasterStatistics:
    """Calculate statistics from already-filtered finite values."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        raise IndicatorDataError(
            f"Dataset {source!r} contains no valid pixels for {indicator}."
        )
    if total_pixel_count < values.size:
        raise IndicatorDataError("Valid pixel count cannot exceed total pixel count.")

    return RasterStatistics(
        indicator=indicator,
        source=source,
        unit=unit,
        total_pixel_count=int(total_pixel_count),
        valid_pixel_count=int(values.size),
        nodata_pixel_count=int(total_pixel_count - values.size),
        mean=float(np.mean(values)),
        minimum=float(np.min(values)),
        maximum=float(np.max(values)),
        standard_deviation=float(np.std(values, ddof=0)),
    )


def analyze_single_band(
    raster_path: str | Path,
    *,
    indicator: str,
    unit: str,
    band: int = 1,
    value_transform: Callable[[np.ma.MaskedArray], np.ma.MaskedArray] | None = None,
    valid_range: tuple[float | None, float | None] | None = None,
    notes: tuple[str, ...] = (),
) -> RasterIndicatorResult:
    """Analyze one real raster band using consistent statistics."""
    source = str(Path(raster_path))
    values, total_pixels, _ = read_valid_values(
        raster_path,
        band=band,
        value_transform=value_transform,
        valid_range=valid_range,
    )
    statistics = statistics_from_values(
        values,
        total_pixel_count=total_pixels,
        indicator=indicator,
        unit=unit,
        source=source,
    )
    return RasterIndicatorResult(
        indicator=indicator,
        status="available",
        unit=unit,
        source=source,
        statistics=statistics,
        notes=notes,
    )


__all__ = [
    "IndicatorDataError",
    "RasterIndicatorResult",
    "RasterStatistics",
    "analyze_single_band",
    "read_valid_values",
    "statistics_from_values",
]

