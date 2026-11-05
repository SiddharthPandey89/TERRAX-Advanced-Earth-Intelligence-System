"""Environmental indicator routes for the Earth GeoIntelligence ML service.

Endpoints
---------
GET  /indicators/catalog   Indicators the platform supports, and whether a data
                           provider is currently registered for each.
POST /indicators/analyze   Resolve indicators for a region (bbox or GeoJSON).

This module never produces environmental values itself. A value is returned
only when a registered ``IndicatorProvider`` supplies a real reading; otherwise
the indicator is reported as ``unavailable`` (supported, but no data) or
``unsupported`` (not part of the catalog).
"""

import asyncio
import logging
import math
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Literal, Protocol

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/indicators", tags=["indicators"])

MAX_VERTICES = 10_000
MAX_INDICATORS_PER_REQUEST = 20

IndicatorStatus = Literal["available", "unavailable", "unsupported"]


# --------------------------------------------------------------------------- #
# Indicator catalog (definitions only; no data)
# --------------------------------------------------------------------------- #
class IndicatorDefinition(BaseModel):
    name: str
    label: str
    description: str


SUPPORTED_INDICATORS: dict[str, IndicatorDefinition] = {
    d.name: d
    for d in (
        IndicatorDefinition(
            name="temperature",
            label="Temperature",
            description="Surface or near-surface air temperature for the region.",
        ),
        IndicatorDefinition(
            name="rainfall",
            label="Rainfall",
            description="Provider-supplied rainfall or precipitation at a representative point; not an area average.",
        ),
        IndicatorDefinition(
            name="elevation",
            label="Elevation",
            description="USGS 3DEP digital-elevation-model point sample where covered; not an area average.",
        ),
        IndicatorDefinition(
            name="water_availability",
            label="Water availability",
            description="Availability of surface and ground water in the region.",
        ),
        IndicatorDefinition(
            name="water_level",
            label="Water level",
            description="Water level of water bodies or aquifers in the region.",
        ),
        IndicatorDefinition(
            name="forest_density",
            label="Forest density",
            description="Density of forest or tree cover in the region.",
        ),
        IndicatorDefinition(
            name="land_characteristics",
            label="Land characteristics",
            description="Land cover, terrain and related land properties of the region.",
        ),
    )
}


# --------------------------------------------------------------------------- #
# Request schemas
# --------------------------------------------------------------------------- #
def _check_position(position: Any) -> tuple[float, float]:
    if not isinstance(position, (list, tuple)) or len(position) not in (2, 3):
        raise ValueError("Each position must be [longitude, latitude] (optional altitude).")
    for coord in position:
        if isinstance(coord, bool) or not isinstance(coord, (int, float)) or not math.isfinite(coord):
            raise ValueError("Coordinates must be finite numbers.")
    lon, lat = float(position[0]), float(position[1])
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"Longitude {lon} is outside [-180, 180].")
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"Latitude {lat} is outside [-90, 90].")
    return lon, lat


def _polygon_vertices(rings: Any) -> list[tuple[float, float]]:
    if not isinstance(rings, list) or not rings:
        raise ValueError("A polygon must be a non-empty list of linear rings.")
    vertices: list[tuple[float, float]] = []
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValueError("Each linear ring needs at least 4 positions.")
        points = [_check_position(p) for p in ring]
        if points[0] != points[-1]:
            raise ValueError("Each linear ring must be closed (first == last position).")
        vertices.extend(points)
    return vertices


class GeoJSONGeometry(BaseModel):
    """GeoJSON Polygon or MultiPolygon in WGS84 (longitude, latitude)."""

    type: Literal["Polygon", "MultiPolygon"]
    coordinates: list[Any]

    def vertices(self) -> list[tuple[float, float]]:
        if self.type == "Polygon":
            return _polygon_vertices(self.coordinates)
        if not self.coordinates:
            raise ValueError("MultiPolygon needs at least one polygon.")
        vertices: list[tuple[float, float]] = []
        for polygon in self.coordinates:
            vertices.extend(_polygon_vertices(polygon))
        return vertices

    @model_validator(mode="after")
    def _validate_coordinates(self) -> "GeoJSONGeometry":
        if len(self.vertices()) > MAX_VERTICES:
            raise ValueError(f"Geometry exceeds the {MAX_VERTICES} vertex limit.")
        return self


class RegionSummary(BaseModel):
    kind: Literal["bbox", "Polygon", "MultiPolygon"]
    bbox: list[float] = Field(description="[min_lon, min_lat, max_lon, max_lat]")


class RegionInput(BaseModel):
    """A region given as exactly one of ``bbox`` or ``geometry``."""

    bbox: list[float] | None = Field(
        default=None,
        min_length=4,
        max_length=4,
        description="[min_lon, min_lat, max_lon, max_lat]; must not cross the antimeridian.",
    )
    geometry: GeoJSONGeometry | None = None

    @model_validator(mode="after")
    def _validate_region(self) -> "RegionInput":
        if (self.bbox is None) == (self.geometry is None):
            raise ValueError("Provide exactly one of 'bbox' or 'geometry'.")
        if self.bbox is not None:
            if not all(math.isfinite(v) for v in self.bbox):
                raise ValueError("bbox values must be finite numbers.")
            min_lon, min_lat, max_lon, max_lat = self.bbox
            if not (-180.0 <= min_lon < max_lon <= 180.0):
                raise ValueError("bbox longitudes must satisfy -180 <= min_lon < max_lon <= 180.")
            if not (-90.0 <= min_lat < max_lat <= 90.0):
                raise ValueError("bbox latitudes must satisfy -90 <= min_lat < max_lat <= 90.")
        return self

    def summary(self) -> RegionSummary:
        if self.bbox is not None:
            return RegionSummary(kind="bbox", bbox=list(self.bbox))
        assert self.geometry is not None
        vertices = self.geometry.vertices()
        lons = [v[0] for v in vertices]
        lats = [v[1] for v in vertices]
        return RegionSummary(
            kind=self.geometry.type,
            bbox=[min(lons), min(lats), max(lons), max(lats)],
        )


class TimeRange(BaseModel):
    start: date
    end: date

    @model_validator(mode="after")
    def _validate_order(self) -> "TimeRange":
        if self.end < self.start:
            raise ValueError("time_range.end must not be before time_range.start.")
        return self


class IndicatorsRequest(BaseModel):
    region: RegionInput
    indicators: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_INDICATORS_PER_REQUEST,
        description="Indicator names. Omit to request every supported indicator.",
    )
    time_range: TimeRange | None = None

    @field_validator("indicators")
    @classmethod
    def _normalize_indicators(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        names: list[str] = []
        for item in value:
            name = item.strip().lower()
            if not name:
                raise ValueError("Indicator names must not be blank.")
            if len(name) > 64:
                raise ValueError("Indicator names must be at most 64 characters.")
            if name not in names:
                names.append(name)
        return names


# --------------------------------------------------------------------------- #
# Response schemas
# --------------------------------------------------------------------------- #
class IndicatorResult(BaseModel):
    indicator: str
    status: IndicatorStatus
    value: float | None = None
    unit: str | None = None
    details: dict[str, Any] | None = None
    source: str | None = None
    period: TimeRange | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _enforce_status_consistency(self) -> "IndicatorResult":
        if self.status == "available":
            if self.value is None and not self.details:
                raise ValueError("An available indicator needs a value or details.")
            if self.value is not None and not math.isfinite(self.value):
                raise ValueError("Indicator value must be finite.")
            if self.value is not None and not self.unit:
                raise ValueError("A scalar value must include its unit.")
            if not self.source:
                raise ValueError("An available indicator must name its data source.")
            if self.reason is not None:
                raise ValueError("An available indicator must not carry a reason.")
        else:
            if any(x is not None for x in (self.value, self.unit, self.details, self.source, self.period)):
                raise ValueError("Only available indicators may carry data.")
            if not self.reason:
                raise ValueError("A non-available indicator must explain why.")
        return self


class SummaryCounts(BaseModel):
    available: int
    unavailable: int
    unsupported: int


class IndicatorsResponse(BaseModel):
    success: bool = True
    region: RegionSummary
    requested_period: TimeRange | None = None
    results: list[IndicatorResult]
    summary: SummaryCounts
    generated_at: datetime


class CatalogEntry(IndicatorDefinition):
    available: bool = Field(description="True when a data provider is registered.")


class CatalogResponse(BaseModel):
    success: bool = True
    indicators: list[CatalogEntry]


# --------------------------------------------------------------------------- #
# Data provider contract
# --------------------------------------------------------------------------- #
class DataUnavailableError(Exception):
    """Raised by a provider when no real data exists for the region or period."""


class ProviderReading(BaseModel):
    """A real measurement or model output returned by a provider."""

    value: float | None = None
    unit: str | None = None
    details: dict[str, Any] | None = None
    source: str
    period: TimeRange | None = None


class IndicatorProvider(Protocol):
    async def fetch(self, region: RegionInput, time_range: TimeRange | None) -> ProviderReading:
        """Return a real reading, or raise ``DataUnavailableError``."""
        ...


_PROVIDERS: dict[str, IndicatorProvider] = {}


def register_provider(indicator: str, provider: IndicatorProvider) -> None:
    """Attach a data provider to a supported indicator (call at startup)."""
    if indicator not in SUPPORTED_INDICATORS:
        raise ValueError(f"Unsupported indicator: {indicator!r}")
    if indicator in _PROVIDERS:
        raise ValueError(f"A provider is already registered for {indicator!r}")
    _PROVIDERS[indicator] = provider


# --------------------------------------------------------------------------- #
# Resolution logic
# --------------------------------------------------------------------------- #
def _unavailable(name: str, reason: str) -> IndicatorResult:
    return IndicatorResult(indicator=name, status="unavailable", reason=reason)


async def _resolve(
    name: str, region: RegionInput, time_range: TimeRange | None
) -> IndicatorResult:
    if name not in SUPPORTED_INDICATORS:
        return IndicatorResult(
            indicator=name,
            status="unsupported",
            reason="This indicator is not part of the supported indicator catalog.",
        )

    provider = _PROVIDERS.get(name)
    if provider is None:
        return _unavailable(name, "No data provider is configured for this indicator yet.")

    try:
        reading = await provider.fetch(region, time_range)
        return IndicatorResult(indicator=name, status="available", **reading.model_dump())
    except DataUnavailableError as exc:
        return _unavailable(name, str(exc) or "No data exists for the requested region or period.")
    except Exception:
        logger.exception("Indicator provider failed for %s", name)
        return _unavailable(name, "The data provider failed to return a valid result.")


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.get("/catalog", response_model=CatalogResponse, summary="List supported indicators")
async def get_catalog() -> CatalogResponse:
    return CatalogResponse(
        indicators=[
            CatalogEntry(**definition.model_dump(), available=name in _PROVIDERS)
            for name, definition in SUPPORTED_INDICATORS.items()
        ]
    )


@router.post("/analyze", response_model=IndicatorsResponse, summary="Resolve indicators for a region")
async def analyze_indicators(payload: IndicatorsRequest) -> IndicatorsResponse:
    names = payload.indicators or list(SUPPORTED_INDICATORS)
    results = await asyncio.gather(
        *(_resolve(name, payload.region, payload.time_range) for name in names)
    )
    counts = Counter(result.status for result in results)
    return IndicatorsResponse(
        region=payload.region.summary(),
        requested_period=payload.time_range,
        results=list(results),
        summary=SummaryCounts(
            available=counts["available"],
            unavailable=counts["unavailable"],
            unsupported=counts["unsupported"],
        ),
        generated_at=datetime.now(timezone.utc),
    )
