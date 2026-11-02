"""Ships bound for Bangladesh, worldwide (DS-AIS-01, U-07): `uv run ais-bd-bound --minutes 3`.

aisstream has no receiver in Bangladesh, but ships announce their destination: subscribe
globally to `ShipStaticData` only (one per ship every few minutes, a fraction of the position
traffic), keep those whose AIS destination names a Bangladesh port, and record where each was
seen (aisstream's MetaData carries the last position). Coverage is coastal (terrestrial
receivers): a ship is seen near Singapore, Colombo or China and not mid-ocean.
Writes data/raw/DS-AIS-01/bd_bound/<UTC>.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import UTC, datetime
from typing import Any

from cportal_core.paths import raw_dir
from cportal_core.settings import get_settings
from websockets.asyncio.client import connect

from cportal_connectors.aisstream import URL, decode

# AIS destination is free text (20 chars): "BD CGP", "CHITTAGONG", "BDCGP>SGSIN", "CTG BD", …
BD = re.compile(
    r"(CHIT+AGONG|CHATTOGRAM|\bCTG\b|BD\s?CGP|CGP\s?BD|MONGLA|BD\s?MGL|PAYRA|BD\s?PAY|BANGLADESH)",
    re.IGNORECASE,
)


def port_of(destination: str) -> str | None:
    d = destination.upper()
    if not BD.search(d):
        return None
    if "MONGLA" in d or "MGL" in d:
        return "BDMGL"
    if "PAYRA" in d or "PAY" in d:
        return "BDPAY"
    return "BDCGP"


def eta(raw: dict[str, Any] | None, seen: datetime) -> str | None:
    """AIS ETA has no year: the next occurrence after the sighting."""
    if not raw or not raw.get("Month") or not raw.get("Day"):
        return None
    try:
        hour, minute = int(raw.get("Hour") or 0) % 24, int(raw.get("Minute") or 0) % 60
        when = datetime(seen.year, int(raw["Month"]), int(raw["Day"]), hour, minute, tzinfo=UTC)
    except ValueError:
        return None
    if when < seen and (seen - when).days > 30:
        when = when.replace(year=seen.year + 1)
    return when.isoformat()


async def collect(minutes: float) -> dict[str, Any]:
    key = get_settings().secret("AISSTREAM_API_KEY")
    if not key:
        raise SystemExit("no AISSTREAM_API_KEY")
    sub = {
        "APIKey": key,
        "BoundingBoxes": [[[-90, -180], [90, 180]]],
        "FilterMessageTypes": ["ShipStaticData"],
    }
    ships: dict[int, dict[str, Any]] = {}
    seen_static = 0
    deadline = time.monotonic() + minutes * 60
    async with connect(URL, open_timeout=20) as ws:
        await ws.send(json.dumps(sub))
        while time.monotonic() < deadline:
            try:
                frame = await asyncio.wait_for(
                    ws.recv(), timeout=max(1.0, deadline - time.monotonic())
                )
            except TimeoutError:
                break
            msg = decode(frame)
            if msg.get("MessageType") != "ShipStaticData":
                continue
            seen_static += 1
            body, meta = msg["Message"]["ShipStaticData"], msg.get("MetaData", {})
            port = port_of(str(body.get("Destination") or ""))
            if port is None:
                continue
            at = datetime.now(UTC)
            dim = body.get("Dimension") or {}
            ships[int(meta.get("MMSI") or body.get("UserID"))] = {
                "mmsi": int(meta.get("MMSI") or body.get("UserID")),
                "name": str(body.get("Name") or meta.get("ShipName") or "").strip(),
                "imo": body.get("ImoNumber") or None,
                "destination": str(body.get("Destination")).strip(),
                "port": port,
                "eta": eta(body.get("Eta"), at),
                "lat": meta.get("latitude"),
                "lon": meta.get("longitude"),
                "length_m": (dim.get("A") or 0) + (dim.get("B") or 0) or None,
                "type": body.get("Type"),
                "seen_at": str(meta.get("time_utc") or at.isoformat()),
            }
    return {"minutes": minutes, "static_messages": seen_static, "bd_bound": list(ships.values())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ais-bd-bound")
    ap.add_argument("--minutes", type=float, default=3.0)
    args = ap.parse_args(argv)
    out = asyncio.run(collect(args.minutes))
    d = raw_dir("DS-AIS-01") / "bd_bound"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    f.write_text(json.dumps(out, indent=1))
    print(f"{out['static_messages']} static messages in {args.minutes} min; "
          f"{len(out['bd_bound'])} ships bound for Bangladesh → {f}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
