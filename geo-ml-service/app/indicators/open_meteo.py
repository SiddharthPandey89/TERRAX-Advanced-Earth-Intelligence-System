"""Open-Meteo point-sample adapter for temperature and rainfall indicators.

Values are provider-returned model/weather products at one representative point,
not area averages or direct in-situ measurements. Provenance is included in every
successful response so the UI can classify the output correctly.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

import httpx

from app.api.routes.indicators import DataUnavailableError, IndicatorProvider, ProviderReading, RegionInput, TimeRange

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
MAX_RESPONSE_BYTES = 2_000_000


def _sample_point(region: RegionInput) -> tuple[float, float]:
    if region.bbox is not None:
        west, south, east, north = region.bbox
        if east - west > 5 or north - south > 5:
            raise DataUnavailableError("Open-Meteo integration samples one point only; requested footprint exceeds 5 degrees. Use a smaller region or a documented area dataset.")
        return (west + east) / 2, (south + north) / 2
    try:
        from shapely.geometry import shape
        geometry = shape({"type": region.geometry.type, "coordinates": region.geometry.coordinates})
        point = geometry.representative_point()
        return float(point.x), float(point.y)
    except Exception as exc:
        raise DataUnavailableError("The region geometry could not be reduced to a safe representative point.") from exc


class OpenMeteoIndicatorProvider:
    def __init__(self, indicator: str):
        if indicator not in {"temperature", "rainfall"}:
            raise ValueError("Open-Meteo indicator must be temperature or rainfall.")
        self.indicator = indicator

    async def fetch(self, region: RegionInput, time_range: TimeRange | None) -> ProviderReading:
        longitude, latitude = _sample_point(region)
        historical = time_range is not None and time_range.end < date.today()
        if time_range is not None and time_range.end >= date.today():
            raise DataUnavailableError("Open-Meteo archive requests must end before today; use the current point-weather endpoint for present conditions.")
        if time_range and (time_range.end - time_range.start).days > 3660:
            raise DataUnavailableError("Requested historical period exceeds the supported ten-year query window.")
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": "UTC",
        }
        if historical:
            params.update({
                "start_date": time_range.start.isoformat(),
                "end_date": time_range.end.isoformat(),
                "daily": "temperature_2m_mean,precipitation_sum",
            })
            endpoint = ARCHIVE_URL
        else:
            params.update({
                "current": "temperature_2m,precipitation",
                "forecast_days": 1,
            })
            endpoint = FORECAST_URL
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=4.0), follow_redirects=False) as client:
                response = await client.get(endpoint, params=params)
                response.raise_for_status()
                if len(response.content) > MAX_RESPONSE_BYTES:
                    raise DataUnavailableError("Open-Meteo response exceeded the configured size limit.")
                payload = response.json()
        except DataUnavailableError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise DataUnavailableError("Open-Meteo is unavailable or returned an invalid response.") from exc

        field = "temperature_2m_mean" if historical and self.indicator == "temperature" else (
            "precipitation_sum" if historical else ("temperature_2m" if self.indicator == "temperature" else "precipitation")
        )
        unit = (payload.get("daily_units") or {}).get(field) if historical else (payload.get("current_units") or {}).get(field)
        if historical:
            values = (payload.get("daily") or {}).get(field)
            valid = [float(value) for value in values or [] if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))]
            if not valid:
                raise DataUnavailableError("No valid provider observations were returned for this period and point.")
            value = sum(valid) / len(valid)
            details = {
                "classification": "derived_statistic_from_provider_daily_values",
                "statistic": "mean of returned daily values",
                "daily_observation_count": len(valid),
                "sample_point": {"latitude": latitude, "longitude": longitude},
                "spatial_support": "single representative point; not an area average",
                "source_product": "Open-Meteo Historical Weather API",
            }
            period = time_range
        else:
            raw = (payload.get("current") or {}).get(field)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
                raise DataUnavailableError("Open-Meteo returned no valid current value for this indicator.")
            value = float(raw)
            details = {
                "classification": "provider_current_model_weather_value",
                "provider_time": (payload.get("current") or {}).get("time"),
                "sample_point": {"latitude": latitude, "longitude": longitude},
                "spatial_support": "single representative point; not an area average",
                "source_product": "Open-Meteo Forecast API",
                "measurement_note": "Current model/weather product; not a guaranteed direct sensor measurement.",
            }
            period = None
        if not unit:
            raise DataUnavailableError("Open-Meteo did not identify units for the requested value.")
        return ProviderReading(value=float(value), unit=str(unit), details=details,
                              source="Open-Meteo Forecast API" if not historical else "Open-Meteo Historical Weather API",
                              period=period)


__all__ = ["OpenMeteoIndicatorProvider"]
