"""USGS 3DEP elevation point-sample indicator adapter."""
from __future__ import annotations
import asyncio
from app.api.routes.indicators import DataUnavailableError, IndicatorProvider, ProviderReading, RegionInput, TimeRange
from app.ingestion.registry import ProviderHTTPError, ProviderUnavailableError, InvalidQueryError
from app.ingestion.usgs.elevation import USGSElevationClient

class USGSElevationIndicatorProvider:
    """Return one genuine EPQS source-raster point sample, never an area average."""
    def __init__(self) -> None:
        self.client = USGSElevationClient()

    async def fetch(self, region: RegionInput, time_range: TimeRange | None) -> ProviderReading:
        if time_range is not None:
            raise DataUnavailableError("USGS EPQS is a present-day elevation point service and does not provide a time series.")
        if region.bbox is not None:
            west, south, east, north = region.bbox
            latitude, longitude = (south + north) / 2, (west + east) / 2
        else:
            try:
                from shapely.geometry import shape
                geometry = shape({"type": region.geometry.type, "coordinates": region.geometry.coordinates})
                point = geometry.representative_point()
                latitude, longitude = float(point.y), float(point.x)
            except Exception as exc:
                raise DataUnavailableError("Region could not be reduced to an elevation query point.") from exc
        try:
            result = await asyncio.to_thread(self.client.query_point, latitude, longitude, timeout=8.0, retries=0)
        except (InvalidQueryError, ProviderUnavailableError, ProviderHTTPError) as exc:
            raise DataUnavailableError("USGS EPQS has no available elevation result for this point, or the provider is unavailable.") from exc
        if not result.records:
            raise DataUnavailableError("USGS EPQS returned no elevation record for this point.")
        record = result.records[0]
        try:
            value = float(record["elevation"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DataUnavailableError("USGS EPQS returned no numeric elevation value.") from exc
        if not (-12000 < value < 12000):
            raise DataUnavailableError("USGS EPQS returned an out-of-range or no-data elevation sentinel.")
        return ProviderReading(
            value=value,
            unit=str(record.get("unit") or "Meters"),
            source="USGS 3DEP Elevation Point Query Service",
            details={
                "classification": "provider_elevation_sample_from_source_raster",
                "sample_point": {"latitude": latitude, "longitude": longitude},
                "spatial_support": "single DEM point sample; not an area average",
                "source_product": record.get("source_raster"),
                "source_url": result.source_url,
                "measurement_note": "Elevation is sampled from USGS 3DEP source terrain data; it is not a ground survey at the query instant.",
            },
        )
