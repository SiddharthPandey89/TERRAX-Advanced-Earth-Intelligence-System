"""NASA Earthdata CMR discovery and optional authenticated downloads."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from ..registry import (
    BoundingBox, DateRange, IngestionResult, InvalidQueryError,
    ProviderUnavailableError, bearer_headers, request_json,
)


class NASAEarthdataClient:
    """Client for public CMR metadata search and Earthdata-protected downloads."""

    base_url = "https://cmr.earthdata.nasa.gov/search"

    @property
    def provider_name(self) -> str:
        return "nasa-earthdata"

    def search_collections(self, *, keyword: str | None = None, bbox: BoundingBox | None = None,
                           date_range: DateRange | None = None, page_size: int = 20) -> IngestionResult:
        """Search NASA collection metadata using CMR."""
        page_size = _page_size(page_size)
        params: dict[str, Any] = {"page_size": page_size, "sort_key": "-score"}
        if keyword and keyword.strip(): params["keyword"] = keyword.strip()
        if bbox: params["bounding_box"] = bbox.as_string()
        if date_range: params["temporal"] = date_range.as_iso_interval()
        payload, source_url = request_json(f"{self.base_url}/collections.json", provider=self.provider_name,
                                           params=params, headers=bearer_headers("NASA_EARTHDATA_TOKEN"))
        entries = payload.get("feed", {}).get("entry", []) if isinstance(payload, dict) else []
        if not isinstance(entries, list): raise ProviderUnavailableError("NASA CMR returned an invalid collection feed.")
        return IngestionResult(self.provider_name, "collections",
                               tuple(_collection_record(e) for e in entries if isinstance(e, dict)), source_url,
                               metadata={"page_size": page_size, "cmr_hits": payload.get("hits") if isinstance(payload, dict) else None})

    def search_granules(self, *, collection_concept_id: str | None = None, short_name: str | None = None,
                        bbox: BoundingBox | None = None, date_range: DateRange | None = None,
                        page_size: int = 20) -> IngestionResult:
        """Search granules for a targeted NASA collection."""
        if not collection_concept_id and not short_name:
            raise InvalidQueryError("CMR granule searches require collection_concept_id or short_name.")
        params: dict[str, Any] = {"page_size": _page_size(page_size), "sort_key": "-start_date"}
        if collection_concept_id: params["collection_concept_id"] = collection_concept_id.strip()
        if short_name: params["short_name"] = short_name.strip()
        if bbox: params["bounding_box"] = bbox.as_string()
        if date_range: params["temporal"] = date_range.as_iso_interval()
        payload, source_url = request_json(f"{self.base_url}/granules.json", provider=self.provider_name,
                                           params=params, headers=bearer_headers("NASA_EARTHDATA_TOKEN"))
        entries = payload.get("feed", {}).get("entry", []) if isinstance(payload, dict) else []
        if not isinstance(entries, list): raise ProviderUnavailableError("NASA CMR returned an invalid granule feed.")
        return IngestionResult(self.provider_name, "granules",
                               tuple(_granule_record(e) for e in entries if isinstance(e, dict)), source_url,
                               metadata={"page_size": params["page_size"], "cmr_hits": payload.get("hits") if isinstance(payload, dict) else None})

    def search(self, **kwargs: Any) -> IngestionResult:
        """Registry-compatible alias for granule discovery."""
        return self.search_granules(**kwargs)

    def download(self, url: str, destination: str | Path, *, timeout: float = 60.0) -> Path:
        """Download a caller-selected asset using NASA_EARTHDATA_TOKEN when supplied."""
        if not url.startswith(("https://", "http://")): raise InvalidQueryError("Download URL must be an HTTP(S) URL.")
        if timeout <= 0: raise InvalidQueryError("timeout must be positive.")
        output = Path(destination); output.parent.mkdir(parents=True, exist_ok=True)
        headers = {"User-Agent": "earth-geointelligence-ml-service/0.1"}; headers.update(bearer_headers("NASA_EARTHDATA_TOKEN"))
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as response, output.open("wb") as stream:
                shutil.copyfileobj(response, stream)
        except (OSError, TimeoutError) as exc:
            raise ProviderUnavailableError(f"NASA asset download failed: {url}") from exc
        return output


def _page_size(value: int) -> int:
    if isinstance(value, bool) or not 1 <= value <= 2000: raise InvalidQueryError("page_size must be between 1 and 2000.")
    return value


def _collection_record(entry: dict[str, Any]) -> dict[str, Any]:
    return {key: entry[key] for key in ("id", "short_name", "version", "entry_title", "archive_center") if key in entry}


def _granule_record(entry: dict[str, Any]) -> dict[str, Any]:
    links = entry.get("links", [])
    data_links = [link.get("href") for link in links if isinstance(link, dict) and str(link.get("rel", "")).endswith("#GETDATA")]
    return {key: entry[key] for key in ("id", "title", "time_start", "time_end", "updated", "collection_concept_id") if key in entry} | {"data_urls": data_links}


EarthdataClient = NASAEarthdataClient

__all__ = ["EarthdataClient", "NASAEarthdataClient"]

