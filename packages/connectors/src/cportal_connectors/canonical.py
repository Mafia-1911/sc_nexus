"""Raw response → canonical records (02 §8 "parse"), shared by live, replay and synthetic modes.

A parser is `(body: bytes, ctx: ParseContext) -> list[Record]`. The same parser runs on a live
response, on a committed sample (replay) and on the bytes a synthetic twin renders in the
source's own wire format, so all three modes go through identical code (ADR-010).

`available_at` (SC-01) is when a fact became available to us. Parsers set it from the source's
own publication time where one exists, else from the event time plus the source's measured lag
(PROBE_REPORT), else from when we fetched the response.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from cportal_core.enums import DataMode
from cportal_core.ids import record_id, stable_id
from cportal_core.paths import samples_dir
from cportal_core.schemas.records import Record

GENERATOR_PREFIX = "cportal-sim"


def scenario_uuid(key: str) -> UUID:
    """Scenario keys ("baseline", "cyclone_supplier_delay") → stable UUIDs."""
    return stable_id("scenario", key)


@dataclass(frozen=True)
class ParseContext:
    source_id: str
    data_mode: DataMode = DataMode.REPLAY
    fetched_at: datetime | None = None
    scenario_id: UUID | None = None
    generator_version: str | None = None

    @classmethod
    def synthetic(cls, source_id: str, scenario: str, generator: str) -> ParseContext:
        return cls(
            source_id,
            DataMode.SYNTHETIC,
            fetched_at=None,
            scenario_id=scenario_uuid(scenario),
            generator_version=generator,
        )

    @property
    def is_synthetic(self) -> bool:
        return self.data_mode == DataMode.SYNTHETIC

    def rid(self, table: str, natural_key: object) -> UUID:
        return record_id(table, self.source_id, str(natural_key), self.scenario_id)

    def lineage(
        self, source_record_id: object | None = None, available_at: datetime | None = None
    ) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_record_id": None if source_record_id is None else str(source_record_id)[:256],
            "data_mode": self.data_mode,
            "is_synthetic": self.is_synthetic,
            "scenario_id": self.scenario_id,
            "generator_version": self.generator_version,
            "available_at": available_at if available_at is not None else self.fetched_at,
        }


Parser = Callable[[bytes, ParseContext], list[Record]]


def lagged(ts: datetime | None, lag_h: float) -> datetime | None:
    """Event time plus a source's publication lag (e.g. GFW port visits ~72 h, PortWatch 10 d)."""
    return None if ts is None else ts + timedelta(hours=lag_h)


def parse_ts(value: Any) -> datetime | None:
    """ISO-8601 (with Z or offset), epoch milliseconds, or None. Naive ISO strings are UTC only
    where the caller has established that the source publishes UTC."""
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value / 1000, UTC)
    text = str(value).strip().replace("Z", "+00:00")
    ts = datetime.fromisoformat(text)
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def sample_bytes(ds_id: str, name: str) -> bytes:
    return (samples_dir(ds_id) / name).read_bytes()


def sample_fetched_at(ds_id: str, name: str) -> datetime | None:
    """`captured_at` from the sample's `<stem>.request.json`, written by the probe harness."""
    stem = name.rsplit(".", 1)[0]
    path = samples_dir(ds_id) / f"{stem}.request.json"
    if not path.is_file():
        return None
    captured = json.loads(path.read_text(encoding="utf-8")).get("captured_at")
    return parse_ts(captured)
