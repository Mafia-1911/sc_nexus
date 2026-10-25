"""DS-AIS-01 · aisstream.io live AIS over WebSocket (no history: the collector persists it).

Probe: an invalid-key session, a 5-second worldwide key check (does data flow at all?), then the
protocol's 10-minute capture over the Bangladesh approach box with every message type.
"""

from __future__ import annotations

import json
import statistics
import time
from collections import Counter
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

from cportal_core.areas import bbox, bbox_names
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from cportal_connectors.aisstream import URL, decode, position, subscription
from cportal_connectors.base import Connector, FieldNote, Purpose
from cportal_connectors.harness import ProbeContext

CAPTURE_S = 600
WORLD = [[[-90.0, -180.0], [90.0, 180.0]]]


def session(sub: dict[str, Any], seconds: float, max_frames: int) -> dict[str, Any]:
    """One WebSocket session: subscribe, read until time or frame budget runs out."""
    frames: list[dict[str, Any]] = []
    out: dict[str, Any] = {"frames": frames, "close": None, "error": None}
    start = time.perf_counter()
    try:
        with connect(URL, compression="deflate", open_timeout=10, max_size=2**22) as ws:
            out["connected_ms"] = round((time.perf_counter() - start) * 1000, 1)
            ws.send(json.dumps(sub))
            deadline = time.monotonic() + seconds
            while len(frames) < max_frames and (left := deadline - time.monotonic()) > 0:
                try:
                    frame = ws.recv(timeout=left)
                except TimeoutError:
                    break
                text = frame.decode("utf-8") if isinstance(frame, bytes) else frame
                frames.append({"received_at": datetime.now(UTC).isoformat(), "frame": text})
    except ConnectionClosed as exc:
        rcvd = exc.rcvd
        out["close"] = {
            "code": rcvd.code if rcvd else None,
            "reason": rcvd.reason if rcvd else None,
        }
    except Exception as exc:  # recorded as evidence
        out["error"] = f"{type(exc).__name__}: {exc}"
    out["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 1)
    return out


class AisStream(Connector):
    ds_id = "DS-AIS-01"
    title = "aisstream.io live AIS"
    needs = ("AISSTREAM_API_KEY",)
    field_notes = {
        "capture_bd_approach:MessageType": FieldNote("", "PositionReport, ShipStaticData, ..."),
        "capture_bd_approach:MetaData.MMSI": FieldNote("", "9-digit Maritime Mobile Service ID"),
        "capture_bd_approach:MetaData.time_utc": FieldNote("UTC text", "Receiver timestamp"),
        "capture_bd_approach:MetaData.latitude": FieldNote("deg", "Normalised position"),
        "capture_bd_approach:Message.PositionReport.Sog": FieldNote("knots", "Speed over ground"),
        "capture_bd_approach:Message.PositionReport.NavigationalStatus": FieldNote(
            "AIS code", "0 under way, 1 at anchor, 5 moored, 15 undefined"
        ),
    }

    def probe(self, ctx: ProbeContext) -> None:
        self._record(
            ctx,
            "invalid_key",
            "bad_key",
            subscription("not-a-real-key", ("ctg_outer_anchorage",)),
            10,
            20,
        )
        key = ctx.secret("AISSTREAM_API_KEY")
        if not key:
            return
        world = {"APIKey": key, "BoundingBoxes": WORLD, "FilterMessageTypes": ["PositionReport"]}
        check = self._record(
            ctx,
            "key_check_world_5s",
            "meta",
            world,
            5,
            5000,
            note="worldwide PositionReports for 5 s: proves the key and pipeline",
        )
        ctx.metric("world_messages_per_s", round(self._count(check, "PositionReport") / 5, 1))
        capture = self._record(
            ctx,
            "capture_bd_approach",
            "main",
            subscription(key, ("bay_of_bengal_approach",), types=None),
            CAPTURE_S,
            50_000,
            sample=True,
            note=f"{CAPTURE_S // 60} min, every message type",
        )
        self._coverage(ctx, capture)

    def _record(
        self,
        ctx: ProbeContext,
        name: str,
        purpose: Purpose,
        sub: dict[str, Any],
        seconds: float,
        max_frames: int,
        *,
        sample: bool = False,
        note: str = "",
    ) -> dict[str, Any]:
        result = session(sub, seconds, max_frames)
        body = "\n".join(json.dumps(f, ensure_ascii=False) for f in result["frames"]).encode()
        decoded = [decode(f["frame"]) for f in result["frames"]]
        ctx.record_local(
            name,
            purpose=purpose,
            ext="jsonl",
            content_type="application/x-ndjson",
            request={
                "url": URL,
                "subscription": sub,
                "seconds": seconds,
                "max_frames": max_frames,
                "compression": "permessage-deflate",
            },
            body=body,
            ok=result["error"] is None and bool(result["frames"]),
            error=result["error"],
            latency_ms=result.get("connected_ms"),
            decode=lambda _b, d=decoded: [m for m in d if m.get("MessageType")],
            records="",
            sample=sample,
            note=(note + (f" close={result['close']}" if result["close"] else "")).strip(),
            meta={"close": result["close"], "elapsed_ms": result["elapsed_ms"]},
        )
        result["decoded"] = decoded
        return result

    @staticmethod
    def _count(result: dict[str, Any], message_type: str) -> int:
        return sum(1 for m in result["decoded"] if m.get("MessageType") == message_type)

    @staticmethod
    def _coverage(ctx: ProbeContext, result: dict[str, Any]) -> None:
        decoded = result["decoded"]
        ctx.metric("frames", len(decoded))
        ctx.metric("by_type", dict(Counter(str(m.get("MessageType")) for m in decoded)))
        errors = [m for m in decoded if "error" in m]
        if errors:
            ctx.metric("error_frames", errors[:3])
        confirmations = [m for m in decoded if m.get("MessageType") == "SubscriptionConfirmation"]
        ctx.metric("subscription_confirmation", confirmations[:1])
        areas = {name: bbox(name) for name in bbox_names()}
        vessels: dict[str, set[int]] = {name: set() for name in areas}
        positions: Counter[str] = Counter()
        for m in decoded:
            if (pos := position(m)) is None:
                continue
            for name, box in areas.items():
                if box.contains(pos[1], pos[2]):
                    vessels[name].add(pos[0])
                    positions[name] += 1
        ctx.metric("unique_mmsi_by_area", {k: len(v) for k, v in vessels.items()})
        ctx.metric("positions_by_area", dict(positions))
        times = [datetime.fromisoformat(f["received_at"]) for f in result["frames"]]
        gaps = [(b - a).total_seconds() for a, b in pairwise(times)]
        if gaps:
            ctx.metric(
                "inter_arrival_s",
                {"median": round(statistics.median(gaps), 2), "max": round(max(gaps), 1)},
            )


CONNECTOR = AisStream()
