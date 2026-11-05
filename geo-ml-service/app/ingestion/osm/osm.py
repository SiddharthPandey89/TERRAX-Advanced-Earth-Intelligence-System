"""OpenStreetMap Nominatim place/feature search client."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from ..registry import BoundingBox, IngestionResult, InvalidQueryError, request_json


class NominatimClient:
    """Conservative Nominatim client for user-triggered searches.

    The public OSMF service must not be used for autocomplete, systematic
    extraction, or bulk geocoding. Configure ``OSM_USER_AGENT`` with an
    identifying application and contact string, and use a self-hosted or
    alternate endpoint for larger workloads.
    """

    default_endpoint = "https://nominatim.openstreetmap.org/search"

    def __init__(self, *, endpoint: str | None = None, user_agent: str | None = None,
                 min_interval_seconds: float = 1.0) -> None:
        self.endpoint = (endpoint or os.getenv("OSM_NOMINATIM_URL") or self.default_endpoint).strip()
        self.user_agent = (user_agent or os.getenv("OSM_USER_AGENT", "")).strip()
        if min_interval_seconds < 1.0:
            raise InvalidQueryError("Nominatim interval must be at least 1 second for the public service.")
        self.min_interval_seconds = min_interval_seconds
        self._lock = threading.Lock()
        self._last_request = 0.0

    @property
    def provider_name(self) -> str:
        return "openstreetmap-nominatim"

    def search(self, *, query: str, bbox: BoundingBox | None = None, limit: int = 10,
               language: str = "en") -> IngestionResult:
        """Search OSM place/address features; this is not an autocomplete method."""
        if not self.user_agent:
            raise InvalidQueryError("Set OSM_USER_AGENT to an identifying application/contact string.")
        if not query or not query.strip():
            raise InvalidQueryError("query must not be blank.")
        if not 1 <= limit <= 40:
            raise InvalidQueryError("limit must be between 1 and 40.")
        with self._lock:
            wait = self.min_interval_seconds - (time.monotonic() - self._last_request)
            if wait > 0: time.sleep(wait)
            payload, source_url = request_json(
                self.endpoint,
                provider=self.provider_name,
                params={
                    "q": query.strip(), "format": "jsonv2", "limit": limit,
                    "addressdetails": 1, "accept-language": language.strip() or "en",
                    "viewbox": f"{bbox.west},{bbox.north},{bbox.east},{bbox.south}" if bbox else None,
                    "bounded": 1 if bbox else None,
                },
                headers={
                    "User-Agent": self.user_agent,
                    **({"Referer": os.getenv("OSM_HTTP_REFERER", "").strip()} if os.getenv("OSM_HTTP_REFERER", "").strip() else {}),
                },
            )
            self._last_request = time.monotonic()
        if not isinstance(payload, list):
            raise InvalidQueryError("Nominatim returned an invalid search response.")
        records = tuple(item for item in payload if isinstance(item, dict))
        return IngestionResult(self.provider_name, "osm-search", records, source_url,
                               metadata={"attribution": "© OpenStreetMap contributors", "license": "ODbL 1.0"})


__all__ = ["NominatimClient"]
