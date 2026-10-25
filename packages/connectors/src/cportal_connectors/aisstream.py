"""aisstream.io WebSocket client pieces shared by the DS-AIS-01 probe and the collector.

Contract (aisstream.io/documentation, read 2026-10-26): send the subscription within 3 s;
BoundingBoxes are [[lat, lon], [lat, lon]] corner pairs; at most 1 subscription update per
second; 3 connections per key and per IP; use permessage-deflate (uncompressed connections are
bandwidth-limited from September 2026); never connect from a browser.
"""

from __future__ import annotations

import json
from typing import Any

from cportal_core.areas import bbox

URL = "wss://stream.aisstream.io/v0/stream"
DEFAULT_AREAS = ("bay_of_bengal_approach",)
DEFAULT_TYPES = (
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
    "ShipStaticData",
    "StaticDataReport",
)


def subscription(
    api_key: str,
    areas: tuple[str, ...] = DEFAULT_AREAS,
    types: tuple[str, ...] | None = DEFAULT_TYPES,
) -> dict[str, Any]:
    sub: dict[str, Any] = {
        "APIKey": api_key,
        "BoundingBoxes": [bbox(name).lat_lon_corners() for name in areas],
    }
    if types:
        sub["FilterMessageTypes"] = list(types)
    return sub


def decode(frame: str | bytes) -> dict[str, Any]:
    text = frame.decode("utf-8") if isinstance(frame, bytes) else frame
    message: dict[str, Any] = json.loads(text)
    return message


def position(message: dict[str, Any]) -> tuple[int, float, float] | None:
    """(MMSI, lon, lat) from the normalised MetaData block, if present."""
    meta = message.get("MetaData") or {}
    try:
        return int(meta["MMSI"]), float(meta["longitude"]), float(meta["latitude"])
    except (KeyError, TypeError, ValueError):
        return None
