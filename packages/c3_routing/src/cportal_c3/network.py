"""The road network: a directed graph of OSM edges with time-dependent truck speeds.

Speeds are modelled, never live (C3 §11): a free-flow speed per road class (scaled by the ORS
calibration) times an hour-of-day multiplier, with a Dhaka profile inside the city radius. A
truck about to enter the central-Dhaka ban zone during the ban waits until it opens.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

import networkx as nx
import numpy as np

from cportal_c3.osm import haversine_m
from cportal_c3.priors import Priors


@dataclass(frozen=True)
class Edge:
    u: int
    v: int
    length_m: float
    highway: str
    maxspeed_kmh: float | None
    coords: tuple[tuple[float, float], ...]
    oneway: bool = False


@dataclass(frozen=True)
class Traversal:
    hours: float  # driving plus any ban wait
    ban_wait_h: float
    km: float
    coords: list[tuple[float, float]]
    highways: dict[str, float]  # km by road class


class RoadNet:
    def __init__(self, edges: list[Edge], priors: Priors) -> None:
        self.priors = priors
        road = priors.road
        self.calibration = float(road["calibration"])
        centre = road["dhaka_centre"]
        self.centre = (float(centre["lon"]), float(centre["lat"]))
        self.dhaka_m = float(road["dhaka_radius_km"]) * 1000
        start, end, radius_km, _ = priors.truck_ban()
        self.ban = (start, end, radius_km * 1000)
        self.graph = nx.DiGraph()
        coords: dict[int, tuple[float, float]] = {}
        for e in edges:
            speed = self.free_speed(e)
            mid = e.coords[len(e.coords) // 2]
            to_centre = haversine_m(mid, self.centre)
            attrs = {
                "length_m": e.length_m,
                "highway": e.highway,
                "seconds": e.length_m / (speed / 3.6),
                "speed_kmh": speed,
                "dhaka": to_centre <= self.dhaka_m,
                "ban": to_centre <= self.ban[2],
            }
            self._add(e.u, e.v, attrs, e.coords)
            if not e.oneway:
                self._add(e.v, e.u, attrs, tuple(reversed(e.coords)))
            coords[e.u], coords[e.v] = e.coords[0], e.coords[-1]
        # Keep the largest strongly connected part so every snapped node can reach every other.
        if self.graph.number_of_nodes():
            largest = max(nx.strongly_connected_components(self.graph), key=len)
            self.graph = self.graph.subgraph(largest).copy()
        self.nodes = np.array([n for n in self.graph.nodes], dtype=np.int64)
        self.lonlat = np.array([coords[int(n)] for n in self.nodes], dtype=float).reshape(-1, 2)

    def _add(
        self, u: int, v: int, attrs: dict[str, object], coords: tuple[tuple[float, float], ...]
    ) -> None:
        existing = self.graph.get_edge_data(u, v)
        if existing is None or float(existing["seconds"]) > float(attrs["seconds"]):  # type: ignore[arg-type]
            self.graph.add_edge(u, v, **attrs, coords=coords)

    def free_speed(self, e: Edge) -> float:
        base = self.priors.speed(e.highway)
        if e.maxspeed_kmh:
            base = min(base, e.maxspeed_kmh)  # trucks never beat the posted limit
        return base * self.calibration

    def nearest(self, lat: float, lon: float) -> int:
        dlat = np.radians(self.lonlat[:, 1] - lat)
        dlon = np.radians(self.lonlat[:, 0] - lon) * math.cos(math.radians(lat))
        return int(self.nodes[int(np.argmin(dlat**2 + dlon**2))])

    def path(
        self,
        origin: int,
        dest: int,
        weight: str = "seconds",
        avoid: set[tuple[int, int]] | None = None,
    ) -> list[int]:
        def cost(u: int, v: int, data: dict[str, float]) -> float:
            w = float(data[weight])
            return w * 1.6 if avoid and (u, v) in avoid else w

        return list(nx.dijkstra_path(self.graph, origin, dest, weight=cost))

    def traverse(self, path: list[int], depart: datetime) -> Traversal:
        """Drive `path` from `depart`: hour-of-day speeds, the Dhaka profile, the truck ban."""
        profiles = self.priors.road["profile"]
        start_h, end_h, _ = self.ban
        clock = depart
        waited = 0.0
        km = 0.0
        coords: list[tuple[float, float]] = []
        by_class: dict[str, float] = {}
        for u, v in itertools.pairwise(path):
            data = self.graph[u][v]
            if data["ban"] and _in_window(clock.hour, start_h, end_h):
                opens = clock.replace(hour=end_h % 24, minute=0, second=0, microsecond=0)
                if opens <= clock:
                    opens += timedelta(days=1)
                waited += (opens - clock).total_seconds() / 3600
                clock = opens
            factor = profiles["dhaka" if data["dhaka"] else "corridor"][clock.hour]
            clock += timedelta(seconds=float(data["seconds"]) / factor)
            km += float(data["length_m"]) / 1000
            by_class[data["highway"]] = (
                by_class.get(data["highway"], 0.0) + float(data["length_m"]) / 1000
            )
            pts = data["coords"]
            coords.extend(pts if not coords else pts[1:])
        return Traversal(
            hours=(clock - depart).total_seconds() / 3600,
            ban_wait_h=waited,
            km=km,
            coords=coords,
            highways=by_class,
        )


def _in_window(hour: int, start: int, end: int) -> bool:
    return start <= hour < end if start < end else hour >= start or hour < end
