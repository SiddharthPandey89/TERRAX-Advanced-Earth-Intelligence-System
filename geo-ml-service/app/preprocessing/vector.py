"""Vector geometry utilities used by raster preprocessing operations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform
from shapely.validation import explain_validity


class VectorProcessingError(ValueError):
    """Raised when a vector geometry cannot be validated or transformed."""


def coerce_geometry(value: BaseGeometry | Mapping[str, Any]) -> BaseGeometry:
    """Convert a Shapely geometry or GeoJSON geometry/Feature to Shapely."""
    if isinstance(value, BaseGeometry):
        geometry = value
    elif isinstance(value, Mapping):
        geojson_type = value.get("type")
        if geojson_type == "Feature":
            value = value.get("geometry")
            if not isinstance(value, Mapping):
                raise VectorProcessingError("GeoJSON Feature must contain a geometry.")
        if value.get("type") == "FeatureCollection":
            raise VectorProcessingError("FeatureCollection is not supported; provide one geometry.")
        try:
            geometry = shape(value)
        except (TypeError, ValueError) as exc:
            raise VectorProcessingError("Invalid GeoJSON geometry.") from exc
    else:
        raise VectorProcessingError("Geometry must be a Shapely geometry or GeoJSON mapping.")

    if geometry.is_empty:
        raise VectorProcessingError("Geometry must not be empty.")
    if not geometry.is_valid:
        raise VectorProcessingError(f"Invalid geometry: {explain_validity(geometry)}")
    return geometry


def geometry_to_geojson(value: BaseGeometry | Mapping[str, Any]) -> dict[str, Any]:
    """Validate a geometry and return a JSON-serializable GeoJSON mapping."""
    return dict(mapping(coerce_geometry(value)))


def geometry_bounds(value: BaseGeometry | Mapping[str, Any]) -> tuple[float, float, float, float]:
    """Return ``(min_x, min_y, max_x, max_y)`` for a validated geometry."""
    return tuple(float(bound) for bound in coerce_geometry(value).bounds)  # type: ignore[return-value]


def reproject_geometry(
    value: BaseGeometry | Mapping[str, Any],
    source_crs: str | CRS,
    target_crs: str | CRS,
) -> BaseGeometry:
    """Transform a validated geometry between coordinate reference systems."""
    geometry = coerce_geometry(value)
    try:
        source = CRS.from_user_input(source_crs)
        target = CRS.from_user_input(target_crs)
        transformer = Transformer.from_crs(source, target, always_xy=True)
    except (TypeError, ValueError) as exc:
        raise VectorProcessingError("Invalid source or target CRS.") from exc
    transformed = transform(transformer.transform, geometry)
    if transformed.is_empty or not transformed.is_valid:
        raise VectorProcessingError("CRS transformation produced an invalid geometry.")
    return transformed


__all__ = [
    "VectorProcessingError",
    "coerce_geometry",
    "geometry_bounds",
    "geometry_to_geojson",
    "reproject_geometry",
]

