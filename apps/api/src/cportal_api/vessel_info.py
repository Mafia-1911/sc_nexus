"""DS-VSL-01 (DataDocked, U-07): a ship's owner, manager, class society and P&I insurer.

On demand only: the trial has 20 credits and a lookup costs 3, so nothing is fetched until a
person asks, at most `DAILY_CAP` a day. Every answer is cached on disk (P&I cover renews yearly;
re-fetched after a year). The key stays on the server (AGENTS rule 8). Contact emails and
addresses in the response are kept in the cache but not served.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from cportal_core.paths import repo_root
from cportal_core.settings import get_settings

URL = "https://datadocked.com/api/vessels_operations/get-vessel-management-data"
DAILY_CAP = 5
MAX_AGE = timedelta(days=365)


class LookupError_(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _dir() -> Path:
    d = repo_root() / "data" / "cache" / "DS-VSL-01"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _blank(v: Any) -> str | None:
    s = str(v or "").strip()
    return None if s in ("", "-") else s


def summary(entry: dict[str, Any]) -> dict[str, Any]:
    raw, m = entry.get("data", {}), entry.get("data", {}).get("management", {})
    return {
        "imo": _blank(raw.get("imo")),
        "owner": _blank(m.get("registeredOwner")),
        "manager": _blank(m.get("manager")),
        "class_society": _blank(m.get("ClassificationSociety")),
        "pi_club": _blank(m.get("P&I")),
        "fetched_at": entry.get("fetched_at"),
        "source": "DS-VSL-01 DataDocked",
    }


def cached(ident: str | int | None) -> dict[str, Any] | None:
    if ident is None:
        return None
    f = _dir() / f"{ident}.json"
    if not f.exists():
        return None
    entry: dict[str, Any] = json.loads(f.read_text())
    return summary(entry)


def _ledger() -> tuple[Path, dict[str, int]]:
    f = _dir() / "_ledger.json"
    data: dict[str, int] = json.loads(f.read_text()) if f.exists() else {}
    return f, data


def lookup(ident: str) -> dict[str, Any]:
    f = _dir() / f"{ident}.json"
    if f.exists():
        entry = json.loads(f.read_text())
        fetched = datetime.fromisoformat(entry["fetched_at"])
        if datetime.now(UTC) - fetched < MAX_AGE:
            return summary(entry)
    key = get_settings().secret("DATADOCKED_API_KEY")
    if not key:
        raise LookupError_(503, "no DataDocked key configured")
    ledger_file, ledger = _ledger()
    today = datetime.now(UTC).date().isoformat()
    if ledger.get(today, 0) >= DAILY_CAP:
        raise LookupError_(429, f"daily cap of {DAILY_CAP} lookups reached (trial credits)")
    r = httpx.get(
        URL,
        params={"imo_or_mmsi": ident},
        headers={"x-api-key": key, "accept": "application/json"},
        timeout=30,
    )
    ledger[today] = ledger.get(today, 0) + 1
    ledger_file.write_text(json.dumps(ledger))
    if r.status_code != 200:
        raise LookupError_(502, f"DataDocked answered {r.status_code}")
    entry = {"fetched_at": datetime.now(UTC).isoformat(), "data": r.json()}
    f.write_text(json.dumps(entry))
    return summary(entry)
