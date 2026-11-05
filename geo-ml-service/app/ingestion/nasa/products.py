"""NASA Earthdata product definitions used by the ingestion layer."""

from __future__ import annotations

from dataclasses import dataclass

from ..registry import BoundingBox, DateRange, IngestionResult, InvalidQueryError
from .earthdata import NASAEarthdataClient


@dataclass(frozen=True)
class NASAProduct:
    """A catalog identifier and documented science layers."""

    short_name: str
    version: str
    provider: str
    layers: tuple[str, ...]
    description: str


MODIS_PRODUCTS: dict[str, NASAProduct] = {
    "MOD13Q1": NASAProduct("MOD13Q1", "061", "LPDAAC_ECS", ("250m_16_days_NDVI", "250m_16_days_EVI"), "MODIS Terra Vegetation Indices 16-Day L3 Global 250m."),
    "MOD11A1": NASAProduct("MOD11A1", "061", "LPDAAC_ECS", ("LST_Day_1km", "LST_Night_1km"), "MODIS Terra Land Surface Temperature/Emissivity Daily L3 Global 1km."),
    "MCD12Q1": NASAProduct("MCD12Q1", "061", "LPDAAC_ECS", ("LC_Type1", "LC_Type2", "LC_Type3", "LC_Type4", "LC_Type5", "LC_Prop1"), "MODIS Terra and Aqua Land Cover Type Yearly L3 Global 500m."),
}


def get_product(short_name: str, version: str = "061") -> NASAProduct:
    """Return a known product definition without claiming data availability."""
    key = short_name.strip().upper()
    try: product = MODIS_PRODUCTS[key]
    except KeyError as exc: raise InvalidQueryError(f"Unsupported NASA product: {short_name!r}.") from exc
    if product.version != version: raise InvalidQueryError(f"Product {key} is defined only at version {product.version}.")
    return product


def search_modis_granules(client: NASAEarthdataClient, product: str | NASAProduct, *, bbox: BoundingBox,
                          date_range: DateRange | None = None, page_size: int = 20) -> IngestionResult:
    """Discover MODIS granules intersecting a bbox and optional date range."""
    definition = get_product(product.short_name, product.version) if isinstance(product, NASAProduct) else get_product(product)
    return client.search_granules(short_name=definition.short_name, bbox=bbox, date_range=date_range, page_size=page_size)


__all__ = ["MODIS_PRODUCTS", "NASAProduct", "get_product", "search_modis_granules"]

