"""`uv run cportal-worker`: one process for schedules, live fetches, AIS replay and the outbox.

Environment:
- CPORTAL_LIVE=0 disables live fetching (offline demo; replay data stays in place).
- CPORTAL_REPLAY_SCENARIO (default cyclone_supplier_delay), CPORTAL_REPLAY_SPEED (default 30),
  CPORTAL_REPLAY_TICK_S (default 5); CPORTAL_REPLAY_SCENARIO="" turns the AIS replay off.
"""

from __future__ import annotations

import json
import logging
import os
import random
import select
import signal
import sys
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from cportal_core.settings import get_settings

from cportal_worker import outbox, sources
from cportal_worker.replay import AisReplay

log = logging.getLogger("cportal_worker")


class JsonFormatter(logging.Formatter):
    """Structured logs (02 §13): one JSON object per line, with any `extra` fields."""

    RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        out |= {k: v for k, v in vars(record).items() if k not in self.RESERVED}
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def listen(stop: threading.Event, database_url: str) -> None:
    """LISTEN on 'outbox'; drain on every notification and at least every 30 s (catch-up)."""
    with psycopg.connect(_dsn(database_url), autocommit=True) as conn:
        conn.execute("LISTEN outbox")
        outbox.drain()
        while not stop.is_set():
            ready, _, _ = select.select([conn.fileno()], [], [], 30)
            if ready:
                for _ in conn.notifies(timeout=0):
                    pass
            outbox.drain()


def build_scheduler(live: bool, replay: AisReplay | None) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(
        executors={"default": ThreadPoolExecutor(4)},
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
        timezone="UTC",
    )
    now = datetime.now(UTC)
    if live:
        for i, (ds_id, minutes) in enumerate(sorted(sources.live_sources().items())):
            # Stagger first runs so the worker does not hit every source at once.
            first = now + timedelta(seconds=20 + 25 * i + random.uniform(0, 10))
            scheduler.add_job(
                sources.refresh, "interval", minutes=minutes, args=[ds_id],
                id=f"live:{ds_id}", next_run_time=first,
            )  # fmt: skip
    if replay is not None:
        tick = float(os.environ.get("CPORTAL_REPLAY_TICK_S", "5"))
        scheduler.add_job(replay.tick, "interval", seconds=tick, id="ais:replay", next_run_time=now)
    scheduler.add_job(outbox.drain, "interval", seconds=60, id="outbox:sweep")
    return scheduler


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    settings = get_settings()
    live = os.environ.get("CPORTAL_LIVE", "1") != "0"
    scenario = os.environ.get("CPORTAL_REPLAY_SCENARIO", "cyclone_supplier_delay")
    replay = None
    if scenario:
        replay = AisReplay(scenario, speed=float(os.environ.get("CPORTAL_REPLAY_SPEED", "30")))
        replay.load()
    scheduler = build_scheduler(live, replay)
    stop = threading.Event()

    def shutdown(signum: int, _frame: object) -> None:
        log.info("stopping", extra={"signal": signum})
        stop.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    scheduler.start()
    log.info(
        "worker started",
        extra={
            "live_sources": sorted(sources.live_sources()) if live else [],
            "replay": scenario or None,
            "jobs": [j.id for j in scheduler.get_jobs()],
        },
    )
    try:
        while not stop.is_set():
            try:
                listen(stop, settings.database_url)
            except psycopg.OperationalError as exc:  # db restarting: back off and reconnect
                log.warning("listen connection lost", extra={"error": str(exc)})
                stop.wait(5)
    finally:
        scheduler.shutdown(wait=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
