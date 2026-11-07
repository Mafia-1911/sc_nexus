"""DS-PORT-10 · Chittagong Port Authority public TOS dashboard and PCS (cpatos.gov.bd).

Public pages only (no login), no robots.txt on the site (checked 2026-11-08), fetched one at a
time at least `GAP_S` apart with our User-Agent; some reports take ~25 s to build, so slow pages
are polled rarely (worker schedule). Times on the site are Dhaka local; parsed to UTC here.

Pages and what they give the platform:
- PCS `/pcs/`: every vessel visit (visit ref, rotation, phase INBOUND/ARRIVED/WORKING/COMPLETE/
  DEPARTED, ETA, ATA, berth, operator, agent, ETD, ATD) → port calls, the Ships table, C4 labels.
- TOS `vesselAtBerth.php` / `vesselAtBerth_BreakBulk.php`: berth, berthed-on, ETD, occupation and
  import/export progress per vessel → berth occupancy, real dock times (GFW cannot split them).
- `yardOccupance.php`, `day_wise_lying_container.php`, `last24_hour_position.php`,
  `24HoursperformanceReport.php`, `berthOccupance.php`: yard capacity/used TEU per terminal,
  containers lying, last-24 h handling and monthly berth occupancy → port state (C4, Nexus).
"""

from __future__ import annotations

import gzip
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any

import httpx
from cportal_core.paths import raw_dir

BASE = "https://cpatos.gov.bd"
DHAKA = timezone(timedelta(hours=6))
GAP_S = 3.0
TIMEOUT_S = 90.0
PAGES = {
    "pcs": "/pcs/",
    "at_berth_container": "/tosdashboard/vesselAtBerth.php",
    "at_berth_breakbulk": "/tosdashboard/vesselAtBerth_BreakBulk.php",
    "yard": "/tosdashboard/yardOccupance.php",
    "lying": "/tosdashboard/day_wise_lying_container.php",
    "last24": "/tosdashboard/last24_hour_position.php",
    "performance24": "/tosdashboard/24HoursperformanceReport.php",
    "berth_monthly": "/tosdashboard/berthOccupance.php",
}


# --- HTML tables ---------------------------------------------------------------------------


class _Tables(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = ""

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join(self._cell.split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row) and self.tables:
                self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell += data


def tables(html: str) -> list[list[list[str]]]:
    p = _Tables()
    p.feed(html)
    return p.tables


def _num(v: str) -> float | None:
    s = v.replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _int(v: str) -> int | None:
    n = _num(v)
    return None if n is None else int(n)


def dhaka_ts(v: str) -> datetime | None:
    """'2026/10/08 11:30:00 pm' (PCS) or '07/11/2026 09:36:00' (TOS), Dhaka time → UTC."""
    s = v.strip()
    if not s or s.startswith("0000"):
        return None
    for fmt in ("%Y/%m/%d %I:%M:%S %p", "%Y/%m/%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
                "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S"):  # fmt: skip
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=DHAKA).astimezone(UTC)
        except ValueError:
            continue
    return None


def berth_key(code: str) -> str:
    """'GCB07', 'GCB-7', 'CCT/1', 'NCT-1' → 'GCB7', 'GCB7', 'CCT1', 'NCT1'."""
    s = re.sub(r"[^A-Z0-9]", "", code.upper())
    return re.sub(r"(?<=[A-Z])0+(?=\d)", "", s)


def vessel_key(name: str) -> str:
    """'MV. BETTER VICTORY' / 'M.V. Better Victory' → 'BETTER VICTORY'."""
    s = re.sub(r"[^A-Z0-9 ]", " ", name.upper())
    s = re.sub(r"^\s*(M\s?V|M\s?T|MT|MV|SS)\s+", "", s)
    return " ".join(s.split())


# --- parsers ---------------------------------------------------------------------------------


def parse_pcs(html: str) -> list[dict[str, Any]]:
    want = ["Visit Ref.", "Vessel Name", "Rotation", "Phase", "ETA", "ATA", "Berth", "Operator",
            "Agent", "ETD", "ATD"]  # fmt: skip
    for tab in tables(html):
        if tab and tab[0][: len(want)] == want:
            out = []
            for r in tab[1:]:
                if len(r) < len(want) or not r[0]:
                    continue
                out.append({
                    "visit_ref": r[0], "vessel": r[1], "rotation": r[2], "phase": r[3].upper(),
                    "eta": dhaka_ts(r[4]), "ata": dhaka_ts(r[5]), "berth": r[6] or None,
                    "operator": r[7] or None, "agent": r[8] or None, "etd": dhaka_ts(r[9]),
                    "atd": dhaka_ts(r[10]),
                })  # fmt: skip
            return out
    return []


def _progress(nums: list[int | None]) -> dict[str, Any]:
    """The 18 numbers after capacity on the at-berth report (box, TEU pairs)."""
    n = [x or 0 for x in nums] + [0] * 18
    return {
        "import": {"total_box": n[0], "total_teu": n[1], "discharged_box": n[2],
                   "discharged_teu": n[3], "balance_box": n[4], "balance_teu": n[5]},
        "export": {"total_box": n[6] + n[8], "total_teu": n[7] + n[9],
                   "loaded_box": n[10] + n[12], "loaded_teu": n[11] + n[13],
                   "balance_box": n[14] + n[16], "balance_teu": n[15] + n[17],
                   "empty_box": n[8], "empty_teu": n[9]},
    }  # fmt: skip


def parse_at_berth(html: str) -> list[dict[str, Any]]:
    for tab in tables(html):
        if tab and tab[0][:3] == ["SlNo.", "Berth", "Vessel Name"]:
            out = []
            for r in tab:
                if len(r) < 7 or not r[0].isdigit():
                    continue
                out.append({
                    "berth": r[1] or None, "vessel": r[2], "berthed_on": dhaka_ts(r[3]),
                    "etd": dhaka_ts(r[4]), "occupation": r[5] or None,
                    "capacity_teu": _int(r[6]), **_progress([_int(x) for x in r[7:25]]),
                })  # fmt: skip
            return out
    return []


def parse_yard(html: str) -> list[dict[str, Any]]:
    out = []
    for tab in tables(html):
        if tab and tab[0][:2] == ["YARD", "CAPACITY TUES"]:
            for r in tab[2:]:
                if len(r) >= 7 and _num(r[1]) is not None:
                    out.append({
                        "yard": r[0], "capacity_teu": _int(r[1]), "used_teu": _int(r[2]),
                        "used_pct": _num(r[3]), "free_teu": _int(r[4]), "boxes": _int(r[6]),
                    })  # fmt: skip
    return out


def parse_lying(html: str) -> list[dict[str, Any]]:
    out = []
    for tab in tables(html):
        if tab and tab[0][:2] == ["LOCATION.", "CONTAINER"]:
            for r in tab[2:]:
                if len(r) >= 3 and _num(r[1]) is not None:
                    out.append({"location": r[0], "boxes": _int(r[1]), "teu": _int(r[2])})
    return out


def parse_quantities(html: str) -> dict[str, dict[str, float | None]]:
    """last24_hour_position: titled two-column tables ('Type', 'Quantity')."""
    out: dict[str, dict[str, float | None]] = {}
    for tab in tables(html):
        if len(tab) >= 3 and tab[1][:2] == ["Type", "Quantity"]:
            title = tab[0][0]
            out[title] = {r[0]: _num(r[1]) for r in tab[2:] if len(r) >= 2}
    return out


def parse_performance(html: str) -> list[dict[str, Any]]:
    for tab in tables(html):
        if tab and tab[0][:3] == ["SL", "VESSEL", "ROTATION"]:
            return [
                {"vessel": r[1], "rotation": r[2], "berth": r[3], "agent": r[4],
                 "discharge": _int(r[5]), "loading": _int(r[8]) if len(r) > 8 else None}
                for r in tab[2:] if len(r) >= 6 and r[0].isdigit()
            ]  # fmt: skip
    return []


def parse_berth_monthly(html: str) -> list[dict[str, Any]]:
    for tab in tables(html):
        if tab and tab[0][:3] == ["SlNo.", "Month Name", "Total Vessel"]:
            return [
                {"month": r[1], "vessels": _int(r[2]), "occupied_h": _num(r[3]),
                 "avg_occupied_h": _num(r[4])}
                for r in tab[1:] if len(r) >= 5 and r[0].isdigit()
            ]  # fmt: skip
    return []


PARSERS = {
    "pcs": parse_pcs,
    "at_berth_container": parse_at_berth,
    "at_berth_breakbulk": parse_at_berth,
    "yard": parse_yard,
    "lying": parse_lying,
    "last24": parse_quantities,
    "performance24": parse_performance,
    "berth_monthly": parse_berth_monthly,
}


# --- fetching --------------------------------------------------------------------------------


@dataclass
class Fetched:
    page: str
    url: str
    status: int
    seconds: float
    fetched_at: datetime
    html: str = ""
    error: str | None = None
    parsed: Any = field(default=None)


def fetch(pages: list[str], user_agent: str, archive: bool = True) -> list[Fetched]:
    """Fetch pages one after another (never in parallel), archive the raw HTML, parse it."""
    out: list[Fetched] = []
    with httpx.Client(headers={"User-Agent": user_agent}, timeout=TIMEOUT_S,
                      follow_redirects=True) as client:  # fmt: skip
        for i, page in enumerate(pages):
            if i:
                time.sleep(GAP_S)
            url = BASE + PAGES[page]
            t0 = time.monotonic()
            at = datetime.now(UTC)
            try:
                r = client.get(url)
                f = Fetched(page, url, r.status_code, time.monotonic() - t0, at, r.text)
            except httpx.HTTPError as exc:
                out.append(Fetched(page, url, 0, time.monotonic() - t0, at, error=str(exc)))
                continue
            if f.status == 200:
                if archive:
                    d = raw_dir("DS-PORT-10") / page
                    d.mkdir(parents=True, exist_ok=True)
                    (d / f"{at:%Y%m%dT%H%M%SZ}.html.gz").write_bytes(gzip.compress(f.html.encode()))
                f.parsed = PARSERS[page](f.html)
            else:
                f.error = f"HTTP {f.status}"
            out.append(f)
    return out
