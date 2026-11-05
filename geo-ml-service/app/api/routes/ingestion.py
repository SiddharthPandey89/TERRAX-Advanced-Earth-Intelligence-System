"""Explicit, bounded access to the repository's real provider clients.

Search endpoints return source metadata/records only; they do not claim that a
dataset was downloaded, decoded, or used as an environmental measurement.
"""
from __future__ import annotations

import asyncio
from datetime import date
from functools import lru_cache
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.ingestion.registry import BoundingBox, DateRange, ProviderHTTPError, ProviderUnavailableError, build_default_registry
from app.ingestion.nasa.products import MODIS_PRODUCTS, search_modis_granules
from app.ingestion.nasa.earthdata import NASAEarthdataClient
from app.ingestion.copernicus.sentinel import CopernicusSentinelClient
from app.ingestion.usgs.elevation import USGSElevationClient
from app.ingestion.usgs.geology import USGSGeologyClient
from app.ingestion.osm.osm import NominatimClient

router = APIRouter(prefix="/ingestion", tags=["data providers"])

@lru_cache(maxsize=1)
def _nominatim_client() -> NominatimClient:
    # The client owns the public Nominatim one-request-per-second lock.
    return NominatimClient()

class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    start_date: date | None = None
    end_date: date | None = None
    keyword: str | None = Field(default=None, max_length=200)
    product: Literal["MOD13Q1", "MOD11A1", "MCD12Q1"] = "MOD13Q1"
    collections: list[str] = Field(default_factory=list, max_length=10)
    cloud_cover_max: float | None = Field(default=None, ge=0, le=100)
    query: str | None = Field(default=None, max_length=256)
    rows: int = Field(default=2, ge=1, le=5)
    columns: int = Field(default=2, ge=1, le=5)
    dataset: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("bbox")
    @classmethod
    def valid_bbox(cls, value: list[float] | None) -> list[float] | None:
        if value is not None:
            BoundingBox.from_sequence(value)
        return value

    @model_validator(mode="after")
    def valid_period(self) -> "SearchRequest":
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("Both start_date and end_date must be supplied together.")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date.")
        return self


def _bbox(req: SearchRequest, required: bool = True) -> BoundingBox | None:
    if req.bbox is None:
        if required: raise HTTPException(422, "bbox [west,south,east,north] is required for this provider.")
        return None
    return BoundingBox.from_sequence(req.bbox)


def _period(req: SearchRequest) -> DateRange | None:
    if req.start_date is None: return None
    return DateRange.from_values(req.start_date, req.end_date)


@router.get("/providers")
async def list_providers() -> dict[str, Any]:
    # Listing is configuration-free and makes no external requests.
    return {"success": True, "providers": [
        {"id": "nasa-modis", "name": "NASA Earthdata CMR", "mode": "metadata discovery", "credential": "NASA_EARTHDATA_TOKEN is only needed for protected asset downloads", "products": [{"short_name": p.short_name, "version": p.version, "description": p.description} for p in MODIS_PRODUCTS.values()]},
        {"id": "copernicus-sentinel", "name": "Copernicus Data Space STAC", "mode": "public catalog discovery", "credential": "No key for public STAC discovery; asset access may require provider authorization"},
        {"id": "usgs-elevation", "name": "USGS 3DEP Elevation Point Query Service", "mode": "point elevation samples", "credential": "No API key; coverage is not global"},
        {"id": "usgs-geology", "name": "USGS The National Map", "mode": "product discovery", "credential": "No API key; returned products must be downloaded and processed separately"},
        {"id": "openstreetmap", "name": "OpenStreetMap Nominatim", "mode": "user-triggered place search", "credential": "Configure OSM_USER_AGENT with application/contact information"},
    ]}


@router.post("/{provider}/search")
async def search_provider(provider: str, req: SearchRequest) -> dict[str, Any]:
    key = provider.strip().lower()
    try:
        box = _bbox(req, required=key != "openstreetmap")
        period = _period(req)
        if key == "nasa-modis":
            client = NASAEarthdataClient()
            result = await asyncio.to_thread(search_modis_granules, client, req.product, bbox=box, date_range=period, page_size=req.limit)
        elif key == "copernicus-sentinel":
            if box is None: raise HTTPException(422, "bbox is required.")
            result = await asyncio.to_thread(CopernicusSentinelClient().search_products, bbox=box, collections=req.collections or None, date_range=period, cloud_cover_max=req.cloud_cover_max, limit=req.limit)
        elif key == "usgs-elevation":
            if box is None: raise HTTPException(422, "bbox is required.")
            result = await asyncio.to_thread(USGSElevationClient().sample_bbox, box, rows=req.rows, columns=req.columns)
        elif key == "usgs-geology":
            if box is None: raise HTTPException(422, "bbox is required.")
            result = await asyncio.to_thread(USGSGeologyClient().search_products, bbox=box, dataset=req.dataset, max_items=req.limit)
        elif key == "openstreetmap":
            if not req.query or not req.query.strip(): raise HTTPException(422, "query is required for OpenStreetMap search.")
            result = await asyncio.to_thread(_nominatim_client().search, query=req.query, bbox=box, limit=min(req.limit, 40))
        else:
            raise HTTPException(404, "Unknown provider. List providers at GET /ingestion/providers.")
        response = result.as_dict()
        response["warning"] = "Provider response is not an area analysis. Dataset discovery or point samples do not establish an environmental measurement, resource occurrence, or prospectivity finding."
        return {"success": True, "result": response}
    except HTTPException:
        raise
    except ProviderHTTPError as exc:
        status = 429 if exc.status == 429 else 502
        raise HTTPException(status, "The data provider rejected or could not serve this query.") from exc
    except (ProviderUnavailableError, TimeoutError) as exc:
        raise HTTPException(503, "The data provider is unavailable or timed out.") from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)[:300]) from exc
    except Exception as exc:
        raise HTTPException(503, "The provider query could not be completed.") from exc
