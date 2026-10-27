"""Corridor road graph from the Geofabrik Bangladesh extract (DS-GEO-01, ADR-013).

Two filtered passes keep memory small: truck-relevant highway ways first, then only the nodes
they use. Ways are split at junctions into edges; edges outside the corridor box are dropped.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import osmium

from cportal_c3.priors import Priors


@dataclass(frozen=True)
class RoadSegment:
    way_id: int
    u: int
    v: int
    highway: str
    oneway: bool
    maxspeed_kmh: float | None
    name: str | None
    coords: tuple[tuple[float, float], ...]  # (lon, lat)

    @property
    def length_m(self) -> float:
        return sum(haversine_m(a, b) for a, b in zip(self.coords, self.coords[1:], strict=False))


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 6_371_000 * 2 * math.asin(math.sqrt(h))


def _speed(tag: str | None) -> float | None:
    if not tag:
        return None
    digits = "".join(ch for ch in tag.split(";")[0] if ch.isdigit() or ch == ".")
    try:
        value = float(digits)
    except ValueError:
        return None
    return value * 1.609 if "mph" in tag else value


def extract(pbf: Path, priors: Priors) -> Iterator[RoadSegment]:
    classes = set(priors["highways"])
    box = priors["bbox"]
    ways: list[tuple[int, list[int], str, bool, float | None, str | None]] = []
    uses: Counter[int] = Counter()
    for w in osmium.FileProcessor(str(pbf), osmium.osm.WAY).with_filter(
        osmium.filter.KeyFilter("highway")
    ):
        highway = w.tags.get("highway")
        if not isinstance(w, osmium.osm.Way) or highway is None or highway not in classes:
            continue
        refs = [n.ref for n in w.nodes]
        if len(refs) < 2:
            continue
        oneway = w.tags.get("oneway") in ("yes", "1", "true") or highway.startswith("motorway")
        ways.append(
            (
                w.id,
                refs,
                highway,
                oneway,
                _speed(w.tags.get("maxspeed")),
                w.tags.get("name:en") or w.tags.get("name"),
            )
        )
        uses.update(refs)
        uses[refs[0]] += 1  # endpoints are always junctions
        uses[refs[-1]] += 1
    coords: dict[int, tuple[float, float]] = {}
    for n in osmium.FileProcessor(str(pbf), osmium.osm.NODE).with_filter(
        osmium.filter.IdFilter(uses.keys())
    ):
        if isinstance(n, osmium.osm.Node) and n.location.valid():
            coords[n.id] = (n.location.lon, n.location.lat)

    def inside(p: tuple[float, float]) -> bool:
        return box["west"] <= p[0] <= box["east"] and box["south"] <= p[1] <= box["north"]

    for way_id, refs, highway, oneway, maxspeed, name in ways:
        start = 0
        for i in range(1, len(refs)):
            if uses[refs[i]] < 2 and i < len(refs) - 1:
                continue
            chunk = refs[start : i + 1]
            start = i
            pts = tuple(coords[r] for r in chunk if r in coords)
            if len(pts) < 2 or not (inside(pts[0]) and inside(pts[-1])):
                continue
            yield RoadSegment(way_id, chunk[0], chunk[-1], highway, oneway, maxspeed, name, pts)
