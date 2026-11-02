"""/traffic: the Route Planner's traffic layer (U-07): live where a source has it, modelled always.

Live: Mapbox traffic vector tiles (DS-TRAF-02; TomTom has no Bangladesh coverage, A-103),
proxied so the token never reaches a browser (rule 8), Bangladesh only, cached 5 minutes to
stay inside the free tier. Modelled: C3's own hour-of-day profile (a Dhaka zone and the
corridor) and the central-Dhaka truck ban, labelled as a model, not live data.
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx
from cportal_c3.priors import load_priors
from cportal_core.settings import get_settings
from fastapi import APIRouter, HTTPException, Query, Response

from cportal_api.deps import meta
from cportal_api.schemas import Envelope

router = APIRouter(tags=["traffic"])
TILE = "https://api.mapbox.com/v4/mapbox.mapbox-traffic-v1/{z}/{x}/{y}.vector.pbf"
BD = (20.3, 87.8, 26.9, 92.9)  # lat_min, lon_min, lat_max, lon_max (Bangladesh, with margin)
TTL_S = 300
_cache: dict[tuple[int, int, int], tuple[float, bytes]] = {}
DHAKA = timezone(timedelta(hours=6))
ATTRIBUTION = "© Mapbox © OpenStreetMap"


def _tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    n = 2.0**z

    def lat(yy: float) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))

    return lat(y + 1), x / n * 360 - 180, lat(y), (x + 1) / n * 360 - 180


def _in_bangladesh(z: int, x: int, y: int) -> bool:
    s, w, n, e = _tile_bounds(z, x, y)
    return not (n < BD[0] or s > BD[2] or e < BD[1] or w > BD[3])


@router.get("/traffic/status", response_model=Envelope[dict[str, Any]])
def status() -> Envelope[dict[str, Any]]:
    live = bool(get_settings().secret("MAPBOX_TOKEN"))
    return Envelope(
        data={
            "live": live,
            "live_source": "DS-TRAF-02 Mapbox traffic" if live else None,
            "attribution": ATTRIBUTION if live else None,
            "modelled_source": "C3 hour-of-day profile and truck ban (estimates)",
            "note": "Bangladesh: live congestion lines where Mapbox has them; TomTom has none",
        },
        meta=meta([], None),
    )


@router.get("/traffic/tiles/{z}/{x}/{y}.pbf")
def tile(z: int, x: int, y: int) -> Response:
    if not 6 <= z <= 16 or not _in_bangladesh(z, x, y):
        raise HTTPException(404, "outside the served area")
    token = get_settings().secret("MAPBOX_TOKEN")
    if not token:
        raise HTTPException(404, "no live traffic source configured")
    key = (z, x, y)
    hit = _cache.get(key)
    if hit is not None and time.monotonic() - hit[0] < TTL_S:
        body = hit[1]
    else:
        r = httpx.get(TILE.format(z=z, x=x, y=y), params={"access_token": token}, timeout=15)
        if r.status_code == 404:
            body = b""
        elif r.status_code != 200:
            raise HTTPException(502, f"Mapbox answered {r.status_code}")
        else:
            body = r.content  # httpx has already undone the gzip transfer encoding
        _cache[key] = (time.monotonic(), body)
    if not body:
        return Response(status_code=204)
    return Response(
        content=body,
        media_type="application/x-protobuf",
        headers={"cache-control": f"public, max-age={TTL_S}"},
    )


def _circle(lat: float, lon: float, km: float, n: int = 72) -> list[list[float]]:
    dlat = km / 111.32
    dlon = km / (111.32 * math.cos(math.radians(lat)))
    ring = [
        [round(lon + dlon * math.cos(2 * math.pi * i / n), 5),
         round(lat + dlat * math.sin(2 * math.pi * i / n), 5)]
        for i in range(n)
    ]  # fmt: skip
    return [*ring, ring[0]]


@router.get("/traffic/modelled", response_model=Envelope[dict[str, Any]])
def modelled(
    hour: int | None = Query(default=None, ge=0, le=23, description="Dhaka hour; default now"),
) -> Envelope[dict[str, Any]]:
    """C3's congestion model as map zones for one hour: speed factor in the Dhaka zone and on the
    corridor (1 = free flow), and the central-Dhaka truck ban when it is in force."""
    p = load_priors()
    road = p["road"]
    h = datetime.now(UTC).astimezone(DHAKA).hour if hour is None else hour
    centre = road["dhaka_centre"]
    dhaka = float(road["profile"]["dhaka"][h])
    corridor = float(road["profile"]["corridor"][h])
    start, end, radius_km, _ = p.truck_ban()
    ban = start <= h < end if start < end else (h >= start or h < end)
    features = [
        {
            "type": "Feature",
            "properties": {"zone": "dhaka", "factor": dhaka,
                           "label": f"Dhaka: trucks at {dhaka:.0%} of free-flow speed (modelled)"},
            "geometry": {"type": "Polygon", "coordinates": [_circle(centre["lat"], centre["lon"],
                                                                    float(road["dhaka_radius_km"]))]},
        },
        {
            "type": "Feature",
            "properties": {"zone": "truck_ban", "active": ban,
                           "label": f"Truck ban {start:02d}:00–{end:02d}:00 "
                                    f"({'in force' if ban else 'lifted'})"},
            "geometry": {"type": "Polygon", "coordinates": [_circle(centre["lat"], centre["lon"],
                                                                    float(radius_km))]},
        },
    ]  # fmt: skip
    return Envelope(
        data={
            "hour": h,
            "corridor_factor": corridor,
            "geojson": {"type": "FeatureCollection", "features": features},
            "source": "C3 hour-of-day profile and truck ban (estimates, config/priors/c3.yaml)",
        },
        meta=meta([], None, note="modelled, not live"),
    )
