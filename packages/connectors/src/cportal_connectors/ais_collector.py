"""`uv run ais-collect`: long-running DS-AIS-01 collector (aisstream has no history: persist now).

Writes every frame verbatim, with its receive time, to hourly files in the raw zone:

    data/raw/DS-AIS-01/<YYYY-MM-DD>/<HH>.jsonl      the open hour, flushed every few seconds
    data/raw/DS-AIS-01/<YYYY-MM-DD>/<HH>.jsonl.gz   closed hours
    data/raw/DS-AIS-01/collector_status.json        heartbeat: counts, reconnects, last error

`uv run ais-collect --report` summarises coverage per named area from the files on disk.
In M2 this moves behind `apps/worker` (02-architecture.md §10); the file format stays.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import gzip
import json
import random
import shutil
import signal
import sys
import time
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from cportal_core.areas import bbox, bbox_names
from cportal_core.paths import raw_dir
from cportal_core.settings import get_settings
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from cportal_connectors.aisstream import DEFAULT_AREAS, URL, decode, position, subscription

DS_ID = "DS-AIS-01"
FLUSH_EVERY_S = 5.0
HEARTBEAT_S = 60.0
MAX_BACKOFF_S = 300.0


class HourlyWriter:
    """Appends lines to the current hour's file; gzips each hour once it is over."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.hour: str | None = None
        self.fh: IO[str] | None = None
        self.path: Path | None = None

    def write(self, received: datetime, frame: str) -> None:
        hour = received.strftime("%Y-%m-%d/%H")
        if hour != self.hour:
            self.close()
            self.hour = hour
            self.path = self.root / f"{hour}.jsonl"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.fh = self.path.open("a", encoding="utf-8")
        assert self.fh is not None
        self.fh.write(json.dumps({"received_at": received.isoformat(), "frame": frame}) + "\n")

    def tick(self, now: datetime) -> None:
        """Called on a timer: flush, and close the hour even when no message arrives."""
        if self.fh is not None:
            self.fh.flush()
        if self.hour is not None and now.strftime("%Y-%m-%d/%H") != self.hour:
            self.close()
            self.hour = None

    def close(self) -> None:
        if self.fh is None or self.path is None:
            return
        self.fh.close()
        self.fh = None
        gz = self.path.with_suffix(".jsonl.gz")
        # Append as a new gzip member if a restart already compressed part of this hour.
        with self.path.open("rb") as src, gzip.open(gz, "ab") as dst:
            shutil.copyfileobj(src, dst)
        self.path.unlink()


class Collector:
    def __init__(self, api_key: str, areas: tuple[str, ...], root: Path) -> None:
        self.api_key = api_key
        self.areas = areas
        self.root = root
        self.writer = HourlyWriter(root)
        self.messages = 0
        self.types: Counter[str] = Counter()
        self.mmsi: set[int] = set()
        self.reconnects = 0
        self.last_error: str | None = None
        self.started = datetime.now(UTC)
        self.stopping = asyncio.Event()

    def heartbeat(self) -> None:
        status = {
            "ds_id": DS_ID,
            "areas": self.areas,
            "started_at": self.started.isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "messages": self.messages,
            "unique_mmsi": len(self.mmsi),
            "by_type": dict(self.types),
            "reconnects": self.reconnects,
            "last_error": self.last_error,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "collector_status.json").write_text(json.dumps(status, indent=2) + "\n")
        print(
            f"[{datetime.now(UTC):%Y-%m-%dT%H:%M:%S}Z] messages={self.messages} "
            f"mmsi={len(self.mmsi)} reconnects={self.reconnects}",
            flush=True,
        )

    async def housekeeping(self) -> None:
        last_beat = 0.0
        while not self.stopping.is_set():
            self.writer.tick(datetime.now(UTC))
            if time.monotonic() - last_beat > HEARTBEAT_S:
                self.heartbeat()
                last_beat = time.monotonic()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.stopping.wait(), timeout=FLUSH_EVERY_S)

    async def run(self) -> None:
        keeper = asyncio.create_task(self.housekeeping())
        streamer = asyncio.create_task(self.stream())
        stopper = asyncio.create_task(self.stopping.wait())
        # A quiet stream never yields, so stopping must cancel the reader, not wait for a frame.
        await asyncio.wait({streamer, stopper}, return_when=asyncio.FIRST_COMPLETED)
        self.stopping.set()
        streamer.cancel()
        await asyncio.gather(streamer, keeper, stopper, return_exceptions=True)
        self.writer.close()
        self.heartbeat()

    async def stream(self) -> None:
        backoff = 1.0
        while not self.stopping.is_set():
            try:
                async with connect(
                    URL, compression="deflate", open_timeout=10, max_size=2**22, ping_interval=20
                ) as ws:
                    await ws.send(json.dumps(subscription(self.api_key, self.areas)))
                    backoff = 1.0
                    async for frame in ws:
                        received = datetime.now(UTC)
                        text = frame.decode("utf-8") if isinstance(frame, bytes) else frame
                        self.writer.write(received, text)
                        message = decode(text)
                        if "error" in message:
                            self.last_error = str(message["error"])[:300]
                        self.messages += 1
                        self.types[str(message.get("MessageType"))] += 1
                        if (pos := position(message)) is not None:
                            self.mmsi.add(pos[0])
                        if self.stopping.is_set():
                            break
            except (ConnectionClosed, InvalidStatus, OSError) as exc:  # OSError covers timeouts
                self.last_error = f"{type(exc).__name__}: {exc}"[:300]
            if self.stopping.is_set():
                break
            self.reconnects += 1
            delay = min(MAX_BACKOFF_S, backoff) * (0.5 + random.random())
            print(f"disconnected ({self.last_error}); reconnecting in {delay:.0f}s", flush=True)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.stopping.wait(), timeout=delay)
            backoff = min(MAX_BACKOFF_S, backoff * 2)


def _lines(path: Path) -> Iterator[str]:
    """Stream lines from a closed (.jsonl.gz) or open (.jsonl) hour file."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            yield from fh
    else:
        with path.open(encoding="utf-8") as fh:
            yield from fh


def report(root: Path) -> dict[str, Any]:
    """Coverage from the files on disk: span, messages, vessels and positions per named area."""
    files = sorted(root.glob("*/*.jsonl*"))
    areas = {name: bbox(name) for name in bbox_names()}
    per_area: dict[str, set[int]] = {name: set() for name in areas}
    positions: Counter[str] = Counter()
    types: Counter[str] = Counter()
    modes: Counter[str] = Counter()
    first = last = None
    total = 0
    for path in files:
        for line in _lines(path):
            try:
                row = json.loads(line)
                message = decode(row["frame"])
            except (ValueError, KeyError):
                continue
            total += 1
            first = first or row["received_at"]
            last = row["received_at"]
            types[str(message.get("MessageType"))] += 1
            modes["synthetic" if row.get("is_synthetic") else "live"] += 1
            if (pos := position(message)) is None:
                continue
            mmsi, lon, lat = pos
            for name, box in areas.items():
                if box.contains(lon, lat):
                    per_area[name].add(mmsi)
                    positions[name] += 1
    return {
        "root": str(root),
        "files": len(files),
        "messages": total,
        "by_mode": dict(modes),
        "first": first,
        "last": last,
        "by_type": dict(types),
        "unique_mmsi_by_area": {k: len(v) for k, v in per_area.items()},
        "positions_by_area": dict(positions),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ais-collect", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--areas",
        default=",".join(DEFAULT_AREAS),
        help="comma-separated names from config/areas.yaml",
    )
    parser.add_argument("--report", action="store_true", help="summarise collected coverage")
    parser.add_argument(
        "--root",
        type=Path,
        help="with --report: another folder in the same layout, e.g. "
        "data/synthetic/DS-AIS-01/baseline",
    )
    args = parser.parse_args(argv)
    root = args.root or raw_dir(DS_ID)
    if args.report:
        print(json.dumps(report(root), indent=2))
        return 0
    key = get_settings().secret("AISSTREAM_API_KEY")
    if not key:
        print(
            "AISSTREAM_API_KEY is not set in .env. Sign up at https://aisstream.io, create a "
            "key under Account, add it to .env, then rerun.",
            file=sys.stderr,
        )
        return 2
    collector = Collector(key, tuple(a.strip() for a in args.areas.split(",") if a.strip()), root)

    async def runner() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, collector.stopping.set)
        await collector.run()

    asyncio.run(runner())
    return 0


if __name__ == "__main__":
    sys.exit(main())
