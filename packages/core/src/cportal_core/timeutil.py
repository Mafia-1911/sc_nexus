"""Time rules (04 §4): store `timestamptz` in UTC, display in Asia/Dhaka (UTC+6, no DST)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DHAKA = ZoneInfo("Asia/Dhaka")


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(ts: datetime) -> datetime:
    """Naive datetimes are rejected rather than guessed: every source states its zone."""
    if ts.tzinfo is None:
        raise ValueError(f"naive datetime {ts.isoformat()}: attach the source's time zone")
    return ts.astimezone(UTC)


def dhaka_midnight_utc(day: date) -> datetime:
    """Start of a Dhaka calendar day, in UTC (18:00 UTC on the previous day)."""
    return datetime.combine(day, time(0), DHAKA).astimezone(UTC)


def to_dhaka(ts: datetime) -> datetime:
    return ensure_utc(ts).astimezone(DHAKA)


def hours_between(start: datetime, end: datetime) -> float:
    return (ensure_utc(end) - ensure_utc(start)) / timedelta(hours=1)
