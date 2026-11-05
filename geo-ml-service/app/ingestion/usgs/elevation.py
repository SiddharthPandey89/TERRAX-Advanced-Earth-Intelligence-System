"""USGS 3DEP Elevation Point Query Service ingestion client."""

from __future__ import annotations

import math
from typing import Any, Literal

from ..registry import BoundingBox, IngestionResult, InvalidQueryError, request_json


class USGSElevationClient:
    """Client for real point elevations from the USGS EPQS service.

    EPQS is a point service. ``sample_bbox`` therefore performs a bounded,
    explicit grid of point requests rather than pretending it returns a raster.
    """

    endpoint = "https://epqs.nationalmap.gov/v1/json"

    @property
    def provider_name(self) -> str:
        return "usgs-elevation"

    def query_point(self, latitude: float, longitude: float, *, units: Literal["Meters", "Feet"] = "Meters",
                    timeout: float = 30.0, retries: int = 2) -> IngestionResult:
        """Query one WGS84 latitude/longitude point."""
        _validate_point(latitude, longitude)
        if units not in ("Meters", "Feet"):
            raise InvalidQueryError("units must be 'Meters' or 'Feet'.")
        payload, source_url = request_json(
            self.endpoint,
            provider=self.provider_name,
            params={"x": longitude, "y": latitude, "units": units, "wkid": 4326, "includeDate": "false"},
            timeout=timeout,
            retries=retries,
        )
        if not isinstance(payload, dict) or not _is_number(payload.get("value")):
            raise InvalidQueryError("USGS EPQS returned no numeric elevation for the point.")
        record = {
            "latitude": latitude,
            "longitude": longitude,
            "elevation": float(payload["value"]),
            "unit": str(payload.get("unit") or units),
            "source_raster": payload.get("raster_name") or payload.get("rasterId"),
        }
        return IngestionResult(self.provider_name, "elevation-point", (record,), source_url)

    def sample_bbox(self, bbox: BoundingBox, *, rows: int = 2, columns: int = 2,
                    units: Literal["Meters", "Feet"] = "Meters") -> IngestionResult:
        """Sample a bounded regular grid of real EPQS point measurements."""
        if not 1 <= rows <= 10 or not 1 <= columns <= 10:
            raise InvalidQueryError("rows and columns must each be between 1 and 10.")
        records: list[dict[str, Any]] = []
        for row in range(rows):
            latitude = bbox.south if rows == 1 else bbox.south + row * (bbox.north - bbox.south) / (rows - 1)
            for column in range(columns):
                longitude = bbox.west if columns == 1 else bbox.west + column * (bbox.east - bbox.west) / (columns - 1)
                result = self.query_point(latitude, longitude, units=units)
                records.extend(result.records)
        return IngestionResult(self.provider_name, "elevation-samples", tuple(records), self.endpoint,
                               metadata={"bbox": bbox.as_list(), "rows": rows, "columns": columns, "unit": units})

    def search(self, *, bbox: BoundingBox, **kwargs: Any) -> IngestionResult:
        """Registry-compatible alias for bounded elevation sampling."""
        return self.sample_bbox(bbox, **kwargs)


def _validate_point(latitude: float, longitude: float) -> None:
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           for value in (latitude, longitude)):
        raise InvalidQueryError("Latitude and longitude must be finite numbers.")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise InvalidQueryError("Latitude or longitude is outside WGS84 bounds.")


def _is_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


__all__ = ["USGSElevationClient"]
