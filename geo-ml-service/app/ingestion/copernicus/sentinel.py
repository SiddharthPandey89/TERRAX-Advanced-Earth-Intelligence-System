"""Copernicus Data Space STAC discovery client for Sentinel products."""

from __future__ import annotations

import os
from typing import Any, Iterable

from ..registry import BoundingBox, DateRange, IngestionResult, InvalidQueryError, bearer_headers, request_json


class CopernicusSentinelClient:
    """Search the public Copernicus Data Space STAC catalog."""

    default_endpoint = "https://stac.dataspace.copernicus.eu/v1/search"

    @property
    def provider_name(self) -> str:
        return "copernicus-sentinel"

    def search_products(self, *, bbox: BoundingBox, collections: Iterable[str] | None = None,
                        date_range: DateRange | None = None, cloud_cover_max: float | None = None,
                        limit: int = 50) -> IngestionResult:
        """Search Sentinel STAC items by bbox, collection, temporal range, and cloud cover."""
        if not 1 <= limit <= 10000:
            raise InvalidQueryError("limit must be between 1 and 10000.")
        collection_list = [value.strip() for value in (collections or ()) if value and value.strip()]
        if cloud_cover_max is not None and not 0 <= cloud_cover_max <= 100:
            raise InvalidQueryError("cloud_cover_max must be between 0 and 100 percent.")
        payload: dict[str, Any] = {"bbox": bbox.as_list(), "limit": limit}
        if collection_list: payload["collections"] = collection_list
        if date_range: payload["datetime"] = date_range.as_iso_interval()
        if cloud_cover_max is not None:
            payload["query"] = {"eo:cloud_cover": {"lte": cloud_cover_max}}
        endpoint = os.getenv("COPERNICUS_STAC_URL", self.default_endpoint).strip() or self.default_endpoint
        response, source_url = request_json(endpoint, provider=self.provider_name, method="POST", payload=payload,
                                            headers=bearer_headers("COPERNICUS_ACCESS_TOKEN"))
        if not isinstance(response, dict) or not isinstance(response.get("features"), list):
            raise InvalidQueryError("Copernicus STAC returned an invalid FeatureCollection.")
        records = tuple(feature for feature in response["features"] if isinstance(feature, dict))
        return IngestionResult(self.provider_name, "sentinel-stac-items", records, source_url,
                               metadata={"bbox": bbox.as_list(), "collections": collection_list, "matched": response.get("numberMatched")})

    def search(self, **kwargs: Any) -> IngestionResult:
        return self.search_products(**kwargs)


__all__ = ["CopernicusSentinelClient"]

