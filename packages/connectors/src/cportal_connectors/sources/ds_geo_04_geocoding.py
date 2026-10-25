"""DS-GEO-04 · Nominatim (OSM geocoder, ≤ 1 request/s) and the GeoNames Bangladesh dump."""

from __future__ import annotations

import csv
import io
from collections import Counter
from typing import Any

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.decoders import csv_records, zip_member
from cportal_connectors.harness import ProbeContext

NOMINATIM = "https://nominatim.openstreetmap.org"
GEONAMES_BD = "https://download.geonames.org/export/dump/BD.zip"
GEONAMES_README = "https://download.geonames.org/export/dump/readme.txt"
GEONAMES_COLUMNS = [
    "geonameid",
    "name",
    "asciiname",
    "alternatenames",
    "latitude",
    "longitude",
    "feature_class",
    "feature_code",
    "country_code",
    "cc2",
    "admin1_code",
    "admin2_code",
    "admin3_code",
    "admin4_code",
    "population",
    "elevation",
    "dem",
    "timezone",
    "modification_date",
]
PLACES = [
    "Chattogram Port",
    "Kamalapur Inland Container Depot",
    "Pangaon",
    "Mongla Port",
    "Payra Port",
    "Dhaka Export Processing Zone",
]
# Feature codes worth keeping in the committed sample: ports, harbours, admin units, towns.
SAMPLE_CODES = {
    "PRT",
    "HBR",
    "ANCH",
    "PPLC",
    "PPLA",
    "PPLA2",
    "PPLA3",
    "ADM1",
    "ADM2",
    "ADM3",
    "INDS",
    "RSTN",
    "AIRP",
    "BDG",
    "DCKY",
}


def _geonames(body: bytes) -> list[dict[str, Any]]:
    return csv_records(
        zip_member(body, r"^BD\.txt$"),
        delimiter="\t",
        columns=GEONAMES_COLUMNS,
        text_columns=[c for c in GEONAMES_COLUMNS if c.endswith("_code")],
        limit=None,
    )


def _geonames_sample(body: bytes) -> bytes:
    rows = [
        r
        for r in _geonames(body)
        if r["feature_code"] in SAMPLE_CODES or (r.get("population") or 0) >= 50_000
    ]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=GEONAMES_COLUMNS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


class Geocoding(Connector):
    ds_id = "DS-GEO-04"
    title = "Nominatim + GeoNames dump"
    field_notes = {
        "search_chattogram_port:place_id": FieldNote(
            "", "Nominatim-internal, unstable; key on osm_type+osm_id instead"
        ),
        "search_chattogram_port:importance": FieldNote("0–1", "Ranking score"),
        "geonames_bd:feature_code": FieldNote("", "GeoNames feature code (PRT port, PPLA...)"),
        "geonames_bd:alternatenames": FieldNote("", "Comma-separated variants incl. Bangla"),
        "geonames_bd:modification_date": FieldNote("YYYY-MM-DD", "Last edit"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        common = {
            "format": "jsonv2",
            "countrycodes": "bd",
            "limit": 5,
            "addressdetails": 1,
            "extratags": 1,
        }
        ctx.http(ProbeCall("status", f"{NOMINATIM}/status", "meta", params={"format": "json"}))
        hits: dict[str, int] = {}
        for place in PLACES:
            slug = place.lower().replace(" ", "_")
            result = ctx.http(
                ProbeCall(
                    f"search_{slug}",
                    f"{NOMINATIM}/search",
                    sample=True,
                    records="",
                    params={**common, "q": place},
                )
            )
            hits[place] = len(result.parsed) if isinstance(result.parsed, list) else -1
        ctx.metric("nominatim_hits", hits)
        ctx.http(
            ProbeCall(
                "reverse_bdcgp",
                f"{NOMINATIM}/reverse",
                sample=True,
                params={"format": "jsonv2", "lat": 22.3333, "lon": 91.8333, "zoom": 16},
                note="UN/LOCODE BDCGP coordinate (2220N 09150E)",
            )
        )
        ctx.http(
            ProbeCall(
                "no_match", f"{NOMINATIM}/search", "empty", params={**common, "q": "xqzvkwpt"}
            )
        )
        ctx.http(
            ProbeCall(
                "bad_format",
                f"{NOMINATIM}/search",
                "bad_param",
                params={"q": "Dhaka", "format": "not-a-format"},
            )
        )
        ctx.http(
            ProbeCall(
                "client_timeout",
                f"{NOMINATIM}/search",
                "timeout",
                params={**common, "q": "Dhaka"},
                timeout_s=0.001,
            )
        )
        ctx.http(ProbeCall("geonames_readme", GEONAMES_README, "meta"))
        geonames = ctx.http(
            ProbeCall(
                "geonames_bd",
                GEONAMES_BD,
                decode=_geonames,
                records="",
                sample=True,
                sample_transform=_geonames_sample,
                sample_ext="tsv",
                note="sample keeps ports, admin units, towns ≥ 50k",
            )
        )
        ctx.http(
            ProbeCall(
                "geonames_missing", "https://download.geonames.org/export/dump/XX.zip", "bad_param"
            )
        )
        if isinstance(geonames.parsed, list):
            rows = geonames.parsed
            ctx.metric("geonames_rows", len(rows))
            ctx.metric("geonames_by_class", dict(Counter(r["feature_class"] for r in rows)))
            ctx.metric(
                "geonames_ports",
                sorted(
                    f"{r['name']} ({r['feature_code']})"
                    for r in rows
                    if r["feature_code"] in {"PRT", "HBR", "ANCH", "DCKY"}
                ),
            )
            ctx.metric("geonames_latest_edit", max(str(r["modification_date"]) for r in rows))


CONNECTOR = Geocoding()
