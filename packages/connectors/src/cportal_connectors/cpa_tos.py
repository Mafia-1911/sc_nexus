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
from datetime import UTC, date, datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any

import httpx
from cportal_core.paths import raw_dir

BASE = "https://cpatos.gov.bd"
DHAKA = timezone(timedelta(hours=6))
GAP_S = 3.0
TIMEOUT_S = 90.0
# Date-range report forms (POST fdate/tdate, ISO dates): history back to at least 2023.
FORMS = {
    "sailed": "/tosdashboard/sailed_vessel.php",
    "gate": "/tosdashboard/all_gate_in_out_report.php",
}
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


def _span_h(v: str) -> float | None:
    """'2d 1h 6m' → 49.1 hours."""
    m = re.fullmatch(r"\s*(\d+)d\s*(\d+)h\s*(\d+)m\s*", v)
    return None if m is None else round(int(m[1]) * 24 + int(m[2]) + int(m[3]) / 60, 2)


def parse_sailed(html: str) -> list[dict[str, Any]]:
    """sailed_vessel.php: one row per container vessel that left a berth (berth on, departed,
    occupied time, terminal operator). 'Arrival DateTime' is the berthing time, not the arrival
    at the anchorage."""
    want = ["SlNo.", "Name", "Rotation No", "Berth", "Arrival DateTime", "Departed DateTime"]
    for tab in tables(html):
        for i, row in enumerate(tab):
            if row[: len(want)] != want:
                continue
            out = []
            for r in tab[i + 1 :]:
                if len(r) < 7 or not r[0].isdigit() or not r[1]:
                    continue
                out.append({
                    "vessel": r[1], "rotation": r[2] or None, "berth": r[3] or None,
                    "berthed": dhaka_ts(r[4]), "departed": dhaka_ts(r[5]),
                    "occupied_h": _span_h(r[6]), "operator": (r[7] if len(r) > 7 else "") or None,
                    "comments": (r[8] if len(r) > 8 else "") or None,
                })  # fmt: skip
            return out
    return []


def parse_gate(html: str) -> list[dict[str, Any]]:
    """all_gate_in_out_report.php: boxes in and out per gate per day (header row of gate names,
    each spanning an In and an Out column)."""
    for tab in tables(html):
        for i, row in enumerate(tab):
            if not row or row[0] != "Date" or i + 1 >= len(tab) or tab[i + 1][:2] != ["In", "Out"]:
                continue
            gates = row[1:]
            out = []
            for r in tab[i + 2 :]:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r[0] if r else ""):
                    continue
                n = [_int(x) or 0 for x in r[1:]] + [0] * (2 * len(gates))
                per = {g: {"in": n[2 * k], "out": n[2 * k + 1]} for k, g in enumerate(gates)}
                out.append({
                    "date": r[0], "gates": per,
                    "in": sum(v["in"] for v in per.values()),
                    "out": sum(v["out"] for v in per.values()),
                })  # fmt: skip
            return out
    return []


FORM_PARSERS = {"sailed": parse_sailed, "gate": parse_gate}


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


def fetch_range(
    form: str, start: date, end: date, client: httpx.Client, archive: bool = True
) -> Fetched:
    """POST one date-range report (inclusive dates), archive the raw HTML, parse it."""
    url = BASE + FORMS[form]
    t0 = time.monotonic()
    at = datetime.now(UTC)
    try:
        r = client.post(url, data={"fdate": start.isoformat(), "tdate": end.isoformat()})
    except httpx.HTTPError as exc:
        return Fetched(form, url, 0, time.monotonic() - t0, at, error=str(exc))
    f = Fetched(form, url, r.status_code, time.monotonic() - t0, at, r.text)
    if f.status != 200:
        f.error = f"HTTP {f.status}"
        return f
    if archive:
        d = raw_dir("DS-PORT-10") / form
        d.mkdir(parents=True, exist_ok=True)
        name = f"{start:%Y%m%d}_{end:%Y%m%d}_{at:%Y%m%dT%H%M%SZ}.html.gz"
        (d / name).write_bytes(gzip.compress(f.html.encode()))
    f.parsed = FORM_PARSERS[form](f.html)
    return f
