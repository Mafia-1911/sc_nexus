"""DS-PORT-05 · UN/LOCODE (UNECE): canonical location codes for ports, ICDs and cities.

service.unece.org (the host in the brief) sits behind a Cloudflare JavaScript challenge, so the
probe uses the newer unlocode.unece.org, which serves the "Pre-Release (Latest)" zip directly.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from typing import Any

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.decoders import text_of
from cportal_connectors.harness import ProbeContext

HOST = "https://unlocode.unece.org"
LATEST_ZIP = f"{HOST}/downloads/unlocode-latest.zip"
OLD_HOST_PAGE = "https://service.unece.org/trade/locode/bd.htm"
COLUMNS = [
    "Change",
    "Country",
    "Location",
    "Name",
    "NameWoDiacritics",
    "Subdivision",
    "Function",
    "Status",
    "Date",
    "IATA",
    "Coordinates",
    "Remarks",
]
# Function classifier: 1 port, 2 rail, 3 road, 4 airport, 5 postal, 6 ICD/multimodal, 7 fixed
# transport, B border crossing (UN/CEFACT Recommendation 16).
FUNCTIONS = {
    "1": "port",
    "2": "rail",
    "3": "road",
    "4": "airport",
    "5": "postal",
    "6": "multimodal",
    "7": "fixed",
    "B": "border",
}
WATCH = {"BDCGP": "Chattogram port", "BDMGL": "Mongla", "BDPGN": "Pangaon", "BDDAC": "Dhaka"}


def code_list_rows(body: bytes, country: str | None = None) -> list[dict[str, Any]]:
    """Rows of the CodeListPart CSVs inside the release zip, optionally for one country."""
    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        for name in sorted(zf.namelist()):
            if not re.search(r"CodeListPart\d+\.csv$", name, re.I):
                continue
            for raw in csv.reader(io.StringIO(text_of(zf.read(name)))):
                row = dict(zip(COLUMNS, (c.strip() for c in raw), strict=False))
                if country is None or row.get("Country") == country:
                    row["_part"] = name.rsplit("/", 1)[-1]
                    rows.append(row)
    return rows


def dm_to_decimal(coords: str) -> tuple[float, float] | None:
    """'2220N 09148E' (degrees+minutes) to (lon, lat)."""
    m = re.fullmatch(r"(\d{2})(\d{2})([NS])\s+(\d{3})(\d{2})([EW])", coords.strip())
    if not m:
        return None
    lat = int(m[1]) + int(m[2]) / 60
    lon = int(m[4]) + int(m[5]) / 60
    return (-lon if m[6] == "W" else lon, -lat if m[3] == "S" else lat)


def bd_extract(body: bytes) -> bytes:
    rows = [r for r in code_list_rows(body, "BD") if r.get("Location")]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=[*COLUMNS, "_part"], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


class UnLocode(Connector):
    ds_id = "DS-PORT-05"
    title = "UN/LOCODE (UNECE)"
    field_notes = {
        "latest_zip:Location": FieldNote("", "3-char location code; full code = Country+Location"),
        "latest_zip:Function": FieldNote(
            "",
            "8-char classifier: 1 port, 2 rail, 3 road, 4 air, "
            "5 postal, 6 multimodal/ICD, 7 fixed, B border",
        ),
        "latest_zip:Status": FieldNote("", "AA/AC/AF/AI/AS approved; RL/RQ/RR requested; QQ old"),
        "latest_zip:Coordinates": FieldNote("deg+min", "'DDMMN DDDMME', not decimal degrees"),
        "latest_zip:Date": FieldNote("YYMM", "Last change"),
        "latest_zip:Change": FieldNote(
            "", "+ added, # name changed, X marked for removal, | changed, = reference entry"
        ),
    }

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(
            ProbeCall(
                "old_host_bd_page",
                OLD_HOST_PAGE,
                "meta",
                note="brief's URL; expect the Cloudflare challenge (403)",
            )
        )
        ctx.http(ProbeCall("publications_page", f"{HOST}/publications/", "meta"))
        latest = ctx.http(
            ProbeCall(
                "latest_zip",
                LATEST_ZIP,
                sample=True,
                ext="zip",
                max_bytes=60_000_000,
                decode=lambda b: code_list_rows(b, "BD"),
                records="",
                sample_transform=bd_extract,
                sample_ext="csv",
                timeout_s=120,
                note="Pre-Release (Latest); sample keeps only Bangladesh rows as CSV",
            )
        )
        ctx.http(
            ProbeCall("missing_file", f"{HOST}/downloads/unlocode-does-not-exist.zip", "bad_param")
        )
        ctx.http(ProbeCall("client_timeout", LATEST_ZIP, "timeout", timeout_s=0.001))
        if latest.ok and latest.body:
            self._metrics(ctx, latest.body)

    def _metrics(self, ctx: ProbeContext, body: bytes) -> None:
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            ctx.metric("zip_members", [i.filename for i in zf.infolist()])
        everything = code_list_rows(body)
        ctx.metric("rows_total", len(everything))
        bd = [r for r in code_list_rows(body, "BD") if r.get("Location")]
        ctx.metric("bd_rows", len(bd))
        by_function: dict[str, int] = {}
        for row in bd:
            for ch in row.get("Function", ""):
                if ch in FUNCTIONS:
                    by_function[FUNCTIONS[ch]] = by_function.get(FUNCTIONS[ch], 0) + 1
        ctx.metric("bd_by_function", by_function)
        index = {f"BD{r['Location']}": r for r in bd}
        ctx.metric(
            "watched_codes",
            {
                code: (
                    {
                        k: index[code].get(k)
                        for k in ("Name", "Function", "Status", "Coordinates", "Date")
                    }
                    if code in index
                    else None
                )
                for code in WATCH
            },
        )
        ctx.metric(
            "bd_ports",
            [
                {
                    "code": f"BD{r['Location']}",
                    "name": r["Name"],
                    "function": r["Function"],
                    "status": r["Status"],
                    "coords": r["Coordinates"],
                    "lonlat": dm_to_decimal(r["Coordinates"]) if r["Coordinates"] else None,
                }
                for r in bd
                if r.get("Function", "")[:1] == "1"
            ],
        )
        payra = [
            f"BD{r['Location']} {r['Name']}"
            for r in bd
            if "payra" in r["Name"].lower() or "pyra" in r["Name"].lower()
        ]
        ctx.metric("payra_matches", payra)
        ctx.note("watched codes: " + json.dumps({c: n for c, n in WATCH.items()}))


CONNECTOR = UnLocode()
