"""Shared ingestion contracts, validation, HTTP transport, and provider registry."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class IngestionError(RuntimeError):
    """Base error for provider discovery or data-access failures."""


class InvalidQueryError(IngestionError, ValueError):
    """Raised when a provider query is invalid."""


class ProviderHTTPError(IngestionError):
    """Raised when a provider returns a non-successful HTTP response."""

    def __init__(self, provider: str, status: int, message: str) -> None:
        super().__init__(f"{provider} returned HTTP {status}: {message}")
        self.provider = provider
        self.status = status


class ProviderRateLimitError(ProviderHTTPError):
    """Raised when a provider asks the client to slow down."""


class ProviderUnavailableError(IngestionError):
    """Raised when a provider cannot be reached after bounded retries."""


@dataclass(frozen=True)
class BoundingBox:
    """WGS84 bounding box in west, south, east, north order."""

    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        values = (self.west, self.south, self.east, self.north)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            raise InvalidQueryError("Bounding-box coordinates must be numbers.")
        if not -180 <= self.west < self.east <= 180:
            raise InvalidQueryError("Bounding-box longitudes must satisfy -180 <= west < east <= 180.")
        if not -90 <= self.south < self.north <= 90:
            raise InvalidQueryError("Bounding-box latitudes must satisfy -90 <= south < north <= 90.")

    @classmethod
    def from_sequence(cls, value: tuple[float, float, float, float] | list[float]) -> "BoundingBox":
        if len(value) != 4:
            raise InvalidQueryError("A bounding box requires [west, south, east, north].")
        return cls(*(float(item) for item in value))

    def as_list(self) -> list[float]:
        return [self.west, self.south, self.east, self.north]

    def as_string(self) -> str:
        return ",".join(str(value) for value in self.as_list())

    def as_geojson(self) -> dict[str, Any]:
        return {
            "type": "Polygon",
            "coordinates": [[
                [self.west, self.south],
                [self.east, self.south],
                [self.east, self.north],
                [self.west, self.north],
                [self.west, self.south],
            ]],
        }

    def as_wkt_polygon(self) -> str:
        return (
            f"POLYGON(({self.west} {self.south}, {self.east} {self.south}, "
            f"{self.east} {self.north}, {self.west} {self.north}, "
            f"{self.west} {self.south}))"
        )


@dataclass(frozen=True)
class DateRange:
    """Inclusive UTC date/datetime interval used by temporal providers."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise InvalidQueryError("Date-range end must not be before start.")

    @classmethod
    def from_values(cls, start: date | datetime | str, end: date | datetime | str) -> "DateRange":
        return cls(_to_datetime(start), _to_datetime(end, end_of_day=True))

    def as_iso_interval(self) -> str:
        start = _utc(self.start).isoformat().replace("+00:00", "Z")
        end = _utc(self.end).isoformat().replace("+00:00", "Z")
        return f"{start}/{end}"


@dataclass(frozen=True)
class IngestionResult:
    """Provider result containing only returned metadata or measurements."""

    provider: str
    resource_type: str
    records: tuple[dict[str, Any], ...]
    source_url: str
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "resource_type": self.resource_type,
            "records": [dict(record) for record in self.records],
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at.isoformat(),
            "metadata": dict(self.metadata),
        }


class IngestionProvider(Protocol):
    """Minimal contract required for registration."""

    @property
    def provider_name(self) -> str:
        ...


class ProviderRegistry:
    """Name-to-provider registry with duplicate-registration protection."""

    def __init__(self) -> None:
        self._providers: dict[str, IngestionProvider] = {}

    def register(self, provider: IngestionProvider, *, replace: bool = False) -> None:
        name = provider.provider_name.strip().lower()
        if not name:
            raise InvalidQueryError("Provider name must not be blank.")
        if name in self._providers and not replace:
            raise InvalidQueryError(f"Provider {name!r} is already registered.")
        self._providers[name] = provider

    def get(self, name: str) -> IngestionProvider:
        key = name.strip().lower()
        try:
            return self._providers[key]
        except KeyError as exc:
            raise InvalidQueryError(f"No ingestion provider is registered as {name!r}.") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    def search(self, name: str, **kwargs: Any) -> IngestionResult:
        provider = self.get(name)
        search = getattr(provider, "search", None)
        if not callable(search):
            raise IngestionError(f"Provider {name!r} does not expose a search operation.")
        return search(**kwargs)

    def __contains__(self, name: str) -> bool:
        return name.strip().lower() in self._providers


registry = ProviderRegistry()


def build_default_registry() -> ProviderRegistry:
    """Create a registry with the requested provider clients, without network calls."""
    from .copernicus.sentinel import CopernicusSentinelClient
    from .nasa.earthdata import NASAEarthdataClient
    from .osm.osm import NominatimClient
    from .usgs.elevation import USGSElevationClient
    from .usgs.geology import USGSGeologyClient

    result = ProviderRegistry()
    for provider in (
        NASAEarthdataClient(),
        USGSElevationClient(),
        USGSGeologyClient(),
        NominatimClient(),
        CopernicusSentinelClient(),
    ):
        result.register(provider)
    return result


def _to_datetime(value: date | datetime | str, *, end_of_day: bool = False) -> datetime:
    if isinstance(value, datetime):
        return _utc(value)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        raw = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise InvalidQueryError(f"Invalid date or datetime: {value!r}") from exc
        if end_of_day and "T" not in value and " " not in value:
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return _utc(parsed)
    raise InvalidQueryError(f"Unsupported date value: {value!r}")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _retry_after(headers: Mapping[str, str]) -> float | None:
    value = headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, min(float(value), 30.0))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            return max(0.0, min((_utc(retry_at) - datetime.now(timezone.utc)).total_seconds(), 30.0))
        except (TypeError, ValueError, OverflowError):
            return None


def request_json(
    url: str,
    *,
    provider: str,
    params: Mapping[str, Any] | None = None,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 30.0,
    retries: int = 2,
) -> tuple[Any, str]:
    """Perform bounded JSON HTTP I/O without adding an HTTP dependency."""
    if timeout <= 0 or retries < 0:
        raise InvalidQueryError("timeout must be positive and retries must not be negative.")
    query = urlencode({key: value for key, value in (params or {}).items() if value is not None}, doseq=True)
    request_url = f"{url}?{query}" if query else url
    request_headers = {"Accept": "application/json", "User-Agent": "earth-geointelligence-ml-service/0.1"}
    request_headers.update(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        request = Request(request_url, data=data, headers=request_headers, method=method.upper())
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read()
                try:
                    return json.loads(raw.decode("utf-8")), request_url
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ProviderUnavailableError(f"{provider} returned invalid JSON.") from exc
        except HTTPError as exc:
            body = exc.read(512).decode("utf-8", errors="replace").strip()
            if exc.code == 429:
                if attempt < retries:
                    time.sleep(_retry_after(exc.headers) or min(2.0 ** attempt, 8.0))
                    continue
                raise ProviderRateLimitError(provider, exc.code, body or "rate limit exceeded") from exc
            if exc.code >= 500 and attempt < retries:
                time.sleep(min(2.0 ** attempt, 8.0))
                continue
            raise ProviderHTTPError(provider, exc.code, body or "request failed") from exc
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(2.0 ** attempt, 8.0))
                continue
            raise ProviderUnavailableError(f"{provider} request failed after retries.") from exc

    raise ProviderUnavailableError(f"{provider} request failed.") from last_error


def bearer_headers(token_env: str) -> dict[str, str]:
    token = os.getenv(token_env, "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


__all__ = [
    "BoundingBox", "DateRange", "IngestionError", "IngestionProvider",
    "IngestionResult", "InvalidQueryError", "ProviderHTTPError",
    "ProviderRateLimitError", "ProviderRegistry", "ProviderUnavailableError",
    "bearer_headers", "build_default_registry", "registry", "request_json",
]

