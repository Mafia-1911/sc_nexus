"""PostGIS geometry ↔ GeoJSON for responses (RFC 7946)."""

from __future__ import annotations

from typing import Any

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping


def geojson(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return dict(mapping(to_shape(value)))


def feature(geometry: Any, properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "Feature", "geometry": geojson(geometry), "properties": properties}
