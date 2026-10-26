"""DS-PORT-07 · Chittagong Port Authority "Berthing position & performance of vessels" (PDF).

The first real vessel-level berth data for Chattogram (A-027). Columns are found by x-position
against the header row, because the PDF's text layer sometimes has a single space between
columns. Dates carry no year: the year is inferred from the report date.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from cportal_core.enums import PortCallFlag, PortCallMethod, PortCallStatus, VisitKind, ZoneType
from cportal_core.ids import imo_check_digit_ok, port_id, vessel_id
from cportal_core.schemas.records import (
    PortCallRecord,
    PortStateSnapshotRecord,
    PortZoneRecord,
    Record,
    VesselRecord,
)
from cportal_core.timeutil import DHAKA

from cportal_connectors.canonical import ParseContext

PORT = "BDCGP"
# Column left edges (PDF points) from the header row of the 2026 layout; a word belongs to the
# last column whose edge is left of the word's centre.
COLUMNS = [
    ("berth", 0),
    ("name", 135),
    ("loa", 290),
    ("cargo", 335),
    ("last_port", 393),
    ("flag", 438),
    ("agent", 483),
    ("arrival", 546),
    ("berthing", 590),
    ("shifting", 632),
    ("leaving", 674),
    ("import_disch", 712),
    ("balance_on_board", 754),
    ("export_lifted", 798),
    ("total_on_board", 842),
    ("next_vessel", 895),
]
# Berth codes in the 2026 layout (jetties, terminals, dolphins, moorings, buoys).
_BERTH = re.compile(
    r"^(J/\d+|CCT/\d|NCT-\d|PCT-\d|DOJ-\d|DDJ-\d|KDJ-\d|BB:|SM-\d+|G-\d|CCJ|GSJ|TSP|DD|"
    r"CUFLJ|UTTJ|K\([UA]\)|WBT|MTJ(\(\w+\))?|SPM|CBC)$"
)
_PAGE_NUMBER = re.compile(r"^[–-]?\s*\d{1,2}\s*[–-]?$")
_LOA = re.compile(r"^\d{1,3}\.\d{2}$")
_DATE = re.compile(r"^(\d{2})/(\d{2})(?:/(\d{2}))?$")
_IMO = re.compile(r"\(IMO:(\d{7})\)")
_MARK = re.compile(r"\((GL|F\d|RENAMED:[^)]*|Attach by High Court:[^)]*)\)")
# CPA flag abbreviations → ISO 3166-1 alpha-3 (seen in the reports; unknown ones stay null).
FLAGS = {
    "LIBE": "LBR", "PANA": "PAN", "HONG": "HKG", "SING": "SGP", "MALT": "MLT", "BD": "BGD",
    "THAI": "THA", "MONGO": "MNG", "FIJI": "FJI", "CAMEROON": "CMR", "HONDURAS": "HND",
    "TANZ": "TZA", "UAE": "ARE", "MALA": "MYS", "MARS": "MHL", "CYPR": "CYP", "INDI": "IND",
    "CHIN": "CHN", "VIET": "VNM", "INDO": "IDN", "TOGO": "TGO", "PALA": "PLW",
}  # fmt: skip
BERTH_CLASS = {
    "J": "general_cargo_jetty",
    "CCT": "container_terminal",
    "NCT": "container_terminal",
    "PCT": "container_terminal",
    "DOJ": "oil_jetty",
    "DDJ": "dry_dock_jetty",
    "KDJ": "jetty",
    "BB": "buoy_berth",
    "SM": "swing_mooring",
}


@dataclass
class Row:
    berth: str
    cells: dict[str, list[str]] = field(default_factory=dict)

    def text(self, column: str) -> str:
        return " ".join(self.cells.get(column, [])).strip()


def _infer_year(day: int, month: int, report: date, expect_future: bool) -> date | None:
    """Pick the year that puts the date nearest the report date on the expected side."""
    candidates = []
    for year in (report.year - 1, report.year, report.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    if not candidates:
        return None
    window = (-60, 200) if expect_future else (-400, 60)
    ok = [c for c in candidates if window[0] <= (c - report).days <= window[1]]
    return min(ok or candidates, key=lambda c: abs((c - report).days))


def cpa_date(text: str, report: date, expect_future: bool = False) -> date | None:
    match = _DATE.match(text.strip())
    if not match:
        return None  # "-", "R/A" (meaning unknown) and blanks
    day, month, year = int(match[1]), int(match[2]), match[3]
    if year:
        return date(2000 + int(year), month, day)
    return _infer_year(day, month, report, expect_future)


def _dhaka_midnight(day: date | None) -> datetime | None:
    return None if day is None else datetime.combine(day, time(0), DHAKA).astimezone(UTC)


# Names in the right-hand column start a little left of its header; numbers there are
# on-board figures, so only words with letters count.
NEXT_VESSEL_X0 = 870


def _is_next_vessel(word: dict[str, Any]) -> bool:
    return word["x0"] >= NEXT_VESSEL_X0 and any(c.isalpha() for c in word["text"])


def _column(x_center: float) -> str:
    name = COLUMNS[0][0]
    for col, edge in COLUMNS:
        if x_center >= edge:
            name = col
    return name


def _lines(words: list[dict[str, Any]], tolerance: float = 3.5) -> list[list[dict[str, Any]]]:
    """Group words into text lines by vertical position (tops within `tolerance` points),
    each line sorted left to right. Bucketing by rounded top splits lines at float edges."""
    lines: list[list[dict[str, Any]]] = []
    for w in sorted(words, key=lambda w: w["top"]):
        if lines and w["top"] - lines[-1][0]["top"] <= tolerance:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _berth_line(row: Row, words: list[dict[str, Any]]) -> None:
    """Long vessel names overflow into the LENGTH column, so the name is everything before
    the first length value; after it, words go by x-position."""
    seen_loa = False
    for w in words:
        centre = (w["x0"] + w["x1"]) / 2
        if not seen_loa and _LOA.match(w["text"]) and w["x0"] >= 280:
            row.cells.setdefault("loa", []).append(w["text"])
            seen_loa = True
            continue
        column = "next_vessel" if _is_next_vessel(w) else _column(centre)
        if not seen_loa and column != "next_vessel":
            column = "name"
        elif seen_loa and column in ("name", "loa"):
            column = "cargo"
        row.cells.setdefault(column, []).append(w["text"])


def extract(body: bytes) -> tuple[dict[str, Any], list[Row]]:
    """Header facts and berth rows from the PDF's words."""
    import pdfplumber  # heavy import, only when a CPA report is parsed

    header: dict[str, Any] = {"tide": [], "draught_m": {}}
    rows: list[Row] = []
    with pdfplumber.open(io.BytesIO(body)) as pdf:
        for page in pdf.pages:
            for line in _lines(page.extract_words()):
                texts = [w["text"] for w in line]
                joined = " ".join(texts)
                if m := re.search(r"OF VESSELS: DATED : (\d{2}/\d{2}/\d{4})", joined):
                    header["positions_date"] = datetime.strptime(m[1], "%d/%m/%Y").date()
                if m := re.search(r"^DATED:(\d{2}/\d{2}/\d{4})", texts[-1] if texts else ""):
                    header["published_date"] = datetime.strptime(m[1], "%d/%m/%Y").date()
                for label in ("INWARD", "OUTWARD"):
                    if m := re.search(rf"{label}: (\d+\.\d+)", joined):
                        header["draught_m"][label.lower()] = float(m[1])
                if m := re.search(r"([HL])\.W\.: (\d{4}) (\d+\.\d+)", joined):
                    header["tide"].append(
                        {"type": f"{m[1]}W", "local_time": m[2], "height_m": float(m[3])}
                    )
                first = line[0]
                if first["x0"] < 135 and _BERTH.match(first["text"]):
                    rows.append(Row(first["text"]))
                    _berth_line(rows[-1], line[1:])
                elif rows and first["x0"] >= 135 and not _PAGE_NUMBER.match(joined):
                    # Continuation line ("(G)", "UNDER REPAIR", "(F1)"): pure x-columns.
                    for w in line:
                        column = (
                            "next_vessel"
                            if _is_next_vessel(w)
                            else _column((w["x0"] + w["x1"]) / 2)
                        )
                        rows[-1].cells.setdefault(column, []).append(w["text"])
    return header, rows


def _vessel_name(raw: str) -> tuple[str, list[str]]:
    marks = [
        m.group(1).split(":")[0].strip().lower().replace(" ", "_") for m in _MARK.finditer(raw)
    ]
    name = _MARK.sub("", _IMO.sub("", raw))
    if name.startswith("*"):
        marks.append("star")
        name = name[1:]
    return " ".join(name.split()), marks


def parse_cpa_berthing(body: bytes, ctx: ParseContext) -> list[Record]:
    header, rows = extract(body)
    report = header.get("positions_date")
    if report is None:
        raise ValueError("CPA report date not found ('OF VESSELS: DATED : dd/mm/yyyy')")
    published = header.get("published_date") or report + timedelta(days=1)
    available = _dhaka_midnight(published)
    snapshot_ts = datetime.combine(report, time(23, 59), DHAKA).astimezone(UTC)
    out: list[Record] = []
    occupancy: dict[str, Any] = {}
    zones: dict[str, Any] = {}
    for row in rows:
        code = row.berth.rstrip(":")
        prefix = re.split(r"[/\-(]", code)[0]
        if code not in zones and code != "BB":
            zones[code] = ctx.rid("port_zone", f"{PORT}:berth:{code}")
            out.append(
                PortZoneRecord(
                    id=zones[code],
                    **ctx.lineage(f"berth:{code}", available_at=available),
                    port_id=port_id(PORT),
                    zone_type=ZoneType.BERTH,
                    name=code,
                    attrs={"berth_class": BERTH_CLASS.get(prefix, "other")},
                )
            )
        raw_name = row.text("name")
        imo_match = _IMO.search(raw_name)
        loa_text = row.text("loa")
        if not imo_match or not loa_text:
            if row.text("next_vessel") and code in zones:
                occupancy.setdefault(code, {})["next_vessel"] = row.text("next_vessel")
            continue
        imo = imo_match.group(1)
        name, marks = _vessel_name(raw_name)
        arrival = cpa_date(row.text("arrival"), report)
        berthed = cpa_date(row.text("berthing"), report)
        leaving = cpa_date(row.text("leaving"), report, expect_future=True)
        valid_imo = imo_check_digit_ok(imo)
        vid = vessel_id(imo if valid_imo else None, None, ctx.scenario_id)
        flag = FLAGS.get(row.text("flag"))
        occupancy[code if code != "BB" else f"BB:{imo}"] = {
            "imo": imo,
            "name": name,
            "cargo": row.text("cargo"),
            "agent": row.text("agent"),
            "import_disch": row.text("import_disch") or None,
            "export_lifted": row.text("export_lifted") or None,
            "next_vessel": row.text("next_vessel") or None,
        }
        if vid is None:
            continue  # the PDF's IMO fails the check digit: keep it in the snapshot only
        out.append(
            VesselRecord(
                id=vid,
                **ctx.lineage(imo, available_at=available),
                imo=imo,
                name=name,
                loa_m=float(loa_text),
                flag_iso3=flag,
            )
        )
        flags = [
            PortCallFlag.DATE_PRECISION_DAY,
            PortCallFlag.CENSORED,
            *(f"cpa:{m}" for m in marks),
        ]
        stay_days = (report - (berthed or arrival or report)).days
        if stay_days > 60:
            flags.append(PortCallFlag.LONG_STAY)
        wait_h = (
            (berthed - arrival).days * 24.0 if arrival and berthed and berthed >= arrival else None
        )
        out.append(
            PortCallRecord(
                id=ctx.rid("port_call", f"{imo}:{arrival}"),
                **ctx.lineage(f"{imo}:{arrival}", available_at=available),
                vessel_id=vid,
                port_id=port_id(PORT),
                status=PortCallStatus.ACTIVE,
                visit_kind=VisitKind.BERTH_CALL,
                arrival_ts=_dhaka_midnight(arrival),
                anchorage_start_ts=_dhaka_midnight(arrival),
                anchorage_end_ts=_dhaka_midnight(berthed),
                berth_start_ts=_dhaka_midnight(berthed),
                departure_planned_ts=_dhaka_midnight(leaving),
                waiting_h=wait_h,
                berth_zone_id=zones.get(code),
                censored=True,
                method=PortCallMethod.CPA_REPORT,
                quality_flags=flags,
            )
        )
    out.append(
        PortStateSnapshotRecord(
            id=ctx.rid("port_state_snapshot", f"{PORT}:{report}"),
            **ctx.lineage(f"{PORT}:{report}", available_at=available),
            port_id=port_id(PORT),
            ts=snapshot_ts,
            berth_occupancy=occupancy,
            tide={
                "date": published.isoformat(),  # the tide table is for the publication day
                "events_local": header["tide"],
                "permissible_fw_draught_m": header["draught_m"],
            },
        )
    )
    return out
