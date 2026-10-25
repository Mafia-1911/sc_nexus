"""Named areas of interest (03-data-sources.md §3), loaded from config/areas.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Any

import yaml

from cportal_core.paths import config_dir


@dataclass(frozen=True)
class BBox:
    """Axis-aligned box in WGS84 degrees."""

    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float

    def __post_init__(self) -> None:
        if not (self.lon_min < self.lon_max and self.lat_min < self.lat_max):
            raise ValueError(f"degenerate bbox {self}")

    def contains(self, lon: float, lat: float) -> bool:
        return self.lon_min <= lon <= self.lon_max and self.lat_min <= lat <= self.lat_max

    def overpass(self) -> str:
        """Overpass QL order: south,west,north,east."""
        return f"{self.lat_min},{self.lon_min},{self.lat_max},{self.lon_max}"

    def lat_lon_corners(self) -> list[list[float]]:
        """[[lat_min, lon_min], [lat_max, lon_max]], the corner order aisstream expects."""
        return [[self.lat_min, self.lon_min], [self.lat_max, self.lon_max]]

    def center(self) -> tuple[float, float]:
        """(lon, lat)."""
        return ((self.lon_min + self.lon_max) / 2, (self.lat_min + self.lat_max) / 2)


@dataclass(frozen=True)
class Point:
    lon: float
    lat: float
    source: str


@cache
def _load() -> dict[str, Any]:
    with (config_dir() / "areas.yaml").open(encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    return data


def bbox(name: str) -> BBox:
    raw = _load()["bboxes"][name]
    lon_min, lat_min, lon_max, lat_max = raw["bbox"]
    return BBox(float(lon_min), float(lat_min), float(lon_max), float(lat_max))


def bbox_names() -> list[str]:
    return list(_load()["bboxes"])


def point(name: str) -> Point:
    raw = _load()["points"][name]
    return Point(lon=float(raw["lon"]), lat=float(raw["lat"]), source=str(raw["source"]))
