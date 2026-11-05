"""Land-cover class frequency analysis for categorical raster datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .statistics import IndicatorDataError, read_valid_values


@dataclass(frozen=True)
class LandCoverResult:
    """Class counts from a categorical land-cover raster."""

    indicator: str
    status: str
    source: str
    total_pixel_count: int
    valid_pixel_count: int
    nodata_pixel_count: int
    class_counts: dict[int, int]
    class_labels: dict[int, str]

    def as_dict(self) -> dict[str, object]:
        return {
            "indicator": self.indicator,
            "status": self.status,
            "source": self.source,
            "total_pixel_count": self.total_pixel_count,
            "valid_pixel_count": self.valid_pixel_count,
            "nodata_pixel_count": self.nodata_pixel_count,
            "class_counts": self.class_counts,
            "class_labels": self.class_labels,
        }


def analyze_landcover(
    raster_path: str | Path,
    *,
    band: int = 1,
    class_labels: Mapping[int, str] | None = None,
) -> LandCoverResult:
    """Count observed land-cover class codes without treating codes as quantities."""
    values, total_pixels, _ = read_valid_values(raster_path, band=band)
    if values.size == 0:
        raise IndicatorDataError(f"Dataset {raster_path!s} contains no land-cover classes.")

    rounded = values.astype(int)
    if not (values == rounded).all():
        raise IndicatorDataError("Land-cover raster values must be integer class codes.")

    counts: dict[int, int] = {}
    for value in rounded:
        code = int(value)
        counts[code] = counts.get(code, 0) + 1

    labels = {int(key): str(value) for key, value in (class_labels or {}).items()}
    return LandCoverResult(
        indicator="landcover",
        status="available",
        source=str(Path(raster_path)),
        total_pixel_count=total_pixels,
        valid_pixel_count=int(values.size),
        nodata_pixel_count=int(total_pixels - values.size),
        class_counts=dict(sorted(counts.items())),
        class_labels=labels,
    )


__all__ = ["LandCoverResult", "analyze_landcover"]

