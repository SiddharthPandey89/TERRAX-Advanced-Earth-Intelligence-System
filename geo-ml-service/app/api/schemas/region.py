"""Reusable geographic request and summary schemas."""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_GEOMETRY_VERTICES = 10_000


def _validate_position(position: Any) -> list[float]:
    if not isinstance(position, (list, tuple)) or len(position) not in (2, 3):
        raise ValueError("A position must be [longitude, latitude] with optional altitude.")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in position):
        raise ValueError("Coordinate values must be finite numbers.")
    if any(not math.isfinite(float(value)) for value in position):
        raise ValueError("Coordinate values must be finite numbers.")

    longitude, latitude = float(position[0]), float(position[1])

    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180 degrees.")
    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90 degrees.")

    return [float(value) for value in position]


def _validate_ring(ring: Any) -> list[list[float]]:
    if not isinstance(ring, list) or len(ring) < 4:
        raise ValueError("Each linear ring must contain at least four positions.")

    positions = [_validate_position(position) for position in ring]

    if positions[0][:2] != positions[-1][:2]:
        raise ValueError("Each linear ring must be closed.")

    return positions


class Coordinate(BaseModel):
    """A WGS84 geographic point represented as latitude and longitude."""

    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @field_validator("latitude", "longitude")
    @classmethod
    def validate_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Coordinate values must be finite numbers.")
        return value


class BoundingBox(BaseModel):
    """An axis-aligned WGS84 bounding box that does not cross the antimeridian."""

    model_config = ConfigDict(extra="forbid")

    min_longitude: float = Field(ge=-180, le=180)
    min_latitude: float = Field(ge=-90, le=90)
    max_longitude: float = Field(ge=-180, le=180)
    max_latitude: float = Field(ge=-90, le=90)

    @field_validator("min_longitude", "min_latitude", "max_longitude", "max_latitude")
    @classmethod
    def validate_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Bounding-box coordinates must be finite numbers.")
        return value

    @model_validator(mode="after")
    def validate_order(self) -> "BoundingBox":
        if self.min_longitude >= self.max_longitude:
            raise ValueError("min_longitude must be less than max_longitude.")
        if self.min_latitude >= self.max_latitude:
            raise ValueError("min_latitude must be less than max_latitude.")
        return self

    def as_list(self) -> list[float]:
        """Return [min_longitude, min_latitude, max_longitude, max_latitude]."""
        return [
            self.min_longitude,
            self.min_latitude,
            self.max_longitude,
            self.max_latitude,
        ]


class GeoJSONGeometry(BaseModel):
    """A validated WGS84 GeoJSON Polygon or MultiPolygon."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["Polygon", "MultiPolygon"]
    coordinates: list[Any]

    @model_validator(mode="after")
    def validate_coordinates(self) -> "GeoJSONGeometry":
        if self.type == "Polygon":
            rings = self.coordinates

            if not isinstance(rings, list) or not rings:
                raise ValueError(
                    "Polygon coordinates must contain at least one linear ring."
                )

            validated = [_validate_ring(ring) for ring in rings]
            vertex_count = sum(len(ring) for ring in validated)

        else:
            polygons = self.coordinates

            if not isinstance(polygons, list) or not polygons:
                raise ValueError(
                    "MultiPolygon coordinates must contain at least one polygon."
                )

            validated_polygons = []

            for polygon in polygons:
                if not isinstance(polygon, list) or not polygon:
                    raise ValueError(
                        "Each MultiPolygon member must contain a linear ring."
                    )

                validated_polygons.append(
                    [_validate_ring(ring) for ring in polygon]
                )

            vertex_count = sum(
                len(ring)
                for polygon in validated_polygons
                for ring in polygon
            )

        if vertex_count > MAX_GEOMETRY_VERTICES:
            raise ValueError(
                f"Geometry exceeds the {MAX_GEOMETRY_VERTICES} vertex limit."
            )

        return self


class RegionSummary(BaseModel):
    """Compact region identity suitable for analysis responses."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["point", "bbox", "Polygon", "MultiPolygon"]
    bbox: list[float] = Field(
        description="[min_longitude, min_latitude, max_longitude, max_latitude]"
    )


class GeographicRegion(BaseModel):
    """A named region represented by exactly one supported spatial selector."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=256)
    point: Coordinate | None = None
    bbox: BoundingBox | None = None
    geometry: GeoJSONGeometry | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_one_spatial_selector(self) -> "GeographicRegion":
        selectors = [
            self.point is not None,
            self.bbox is not None,
            self.geometry is not None,
        ]

        if sum(selectors) != 1:
            raise ValueError("Provide exactly one of point, bbox, or geometry.")

        return self

    def summary(self) -> RegionSummary:
        if self.point is not None:
            return RegionSummary(
                kind="point",
                bbox=[
                    self.point.longitude,
                    self.point.latitude,
                    self.point.longitude,
                    self.point.latitude,
                ],
            )

        if self.bbox is not None:
            return RegionSummary(
                kind="bbox",
                bbox=self.bbox.as_list(),
            )

        assert self.geometry is not None

        coordinates = self.geometry.coordinates

        positions = (
            [
                position
                for ring in coordinates
                for position in ring
            ]
            if self.geometry.type == "Polygon"
            else [
                position
                for polygon in coordinates
                for ring in polygon
                for position in ring
            ]
        )

        longitudes = [position[0] for position in positions]
        latitudes = [position[1] for position in positions]

        return RegionSummary(
            kind=self.geometry.type,
            bbox=[
                min(longitudes),
                min(latitudes),
                max(longitudes),
                max(latitudes),
            ],
        )


__all__ = [
    "BoundingBox",
    "Coordinate",
    "GeoJSONGeometry",
    "GeographicRegion",
    "MAX_GEOMETRY_VERTICES",
    "RegionSummary",
]

