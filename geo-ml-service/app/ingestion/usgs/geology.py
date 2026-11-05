"""USGS National Map product-discovery client for geology-related data."""

from __future__ import annotations

import os
from typing import Any

from ..registry import BoundingBox, IngestionResult, InvalidQueryError, request_json


class USGSGeologyClient:
    """Discover downloadable National Map products; it does not invent geology values."""

    endpoint = "https://tnmaccess.nationalmap.gov/api/v1/products"

    @property
    def provider_name(self) -> str:
        return "usgs-geology"

    def search_products(self, *, bbox: BoundingBox, dataset: str | None = None,
                        product_format: str | None = None, max_items: int = 20,
                        offset: int = 0) -> IngestionResult:
        """Search TNMAccess products intersecting a WGS84 bounding box."""
        if not 1 <= max_items <= 1000 or offset < 0:
            raise InvalidQueryError("max_items must be 1-1000 and offset must be non-negative.")
        params: dict[str, Any] = {"bbox": bbox.as_string(), "max": max_items, "offset": offset}
        if dataset and dataset.strip(): params["datasets"] = dataset.strip()
        if product_format and product_format.strip(): params["prodFormats"] = product_format.strip()
        endpoint = os.getenv("USGS_TNM_ENDPOINT", self.endpoint).strip() or self.endpoint
        payload, source_url = request_json(endpoint, provider=self.provider_name, params=params)
        if not isinstance(payload, dict):
            raise InvalidQueryError("USGS TNMAccess returned an invalid product response.")
        items = payload.get("items", payload.get("results", []))
        if not isinstance(items, list):
            raise InvalidQueryError("USGS TNMAccess returned an invalid product list.")
        records = tuple(item for item in items if isinstance(item, dict))
        return IngestionResult(self.provider_name, "national-map-products", records, source_url,
                               metadata={"bbox": bbox.as_list(), "dataset": dataset, "total": payload.get("total")})

    def search(self, **kwargs: Any) -> IngestionResult:
        return self.search_products(**kwargs)


__all__ = ["USGSGeologyClient"]

