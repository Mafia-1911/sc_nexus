"""DS-NEWS-02 · GDELT 2.0 Events + GKG raw files (15-minute updates since 2015)."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from cportal_core.schemas.records import ArticleRecord

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.decoders import csv_records, zip_member
from cportal_connectors.harness import ProbeContext
from cportal_connectors.parsers.news import parse_gdelt_gkg

ROOT = "http://data.gdeltproject.org/gdeltv2"
# GDELT 2.0 Event export, 61 tab-separated columns, no header (GDELT-Event_Codebook-V2.0).
_ACTOR = [
    "Code",
    "Name",
    "CountryCode",
    "KnownGroupCode",
    "EthnicCode",
    "Religion1Code",
    "Religion2Code",
    "Type1Code",
    "Type2Code",
    "Type3Code",
]
_GEO = ["Type", "FullName", "CountryCode", "ADM1Code", "ADM2Code", "Lat", "Long", "FeatureID"]
EVENT_COLUMNS = [
    "GLOBALEVENTID",
    "SQLDATE",
    "MonthYear",
    "Year",
    "FractionDate",
    *(f"Actor1{c}" for c in _ACTOR),
    *(f"Actor2{c}" for c in _ACTOR),
    "IsRootEvent",
    "EventCode",
    "EventBaseCode",
    "EventRootCode",
    "QuadClass",
    "GoldsteinScale",
    "NumMentions",
    "NumSources",
    "NumArticles",
    "AvgTone",
    *(f"Actor1Geo_{c}" for c in _GEO),
    *(f"Actor2Geo_{c}" for c in _GEO),
    *(f"ActionGeo_{c}" for c in _GEO),
    "DATEADDED",
    "SOURCEURL",
]
# GKG 2.1, 27 tab-separated columns (GDELT-Global_Knowledge_Graph_Codebook-V2.1).
GKG_COLUMNS = [
    "GKGRECORDID",
    "DATE",
    "SourceCollectionIdentifier",
    "SourceCommonName",
    "DocumentIdentifier",
    "Counts",
    "V2Counts",
    "Themes",
    "V2Themes",
    "Locations",
    "V2Locations",
    "Persons",
    "V2Persons",
    "Organizations",
    "V2Organizations",
    "V2Tone",
    "Dates",
    "GCAM",
    "SharingImage",
    "RelatedImages",
    "SocialImageEmbeds",
    "SocialVideoEmbeds",
    "Quotations",
    "AllNames",
    "Amounts",
    "TranslationInfo",
    "Extras",
]
assert len(EVENT_COLUMNS) == 61 and len(GKG_COLUMNS) == 27
# CAMEO and geo codes are identifiers: keep "04" and "14" both as text.
EVENT_TEXT = [
    c
    for c in EVENT_COLUMNS
    if c.endswith(("Code", "FeatureID")) or c in ("EventCode", "EventBaseCode", "EventRootCode")
]


def _events(body: bytes) -> list[dict[str, Any]]:
    return csv_records(
        zip_member(body, r"\.CSV$"),
        delimiter="\t",
        columns=EVENT_COLUMNS,
        text_columns=EVENT_TEXT,
        limit=None,
    )


def _gkg(body: bytes) -> list[dict[str, Any]]:
    rows = csv_records(zip_member(body, r"\.csv$"), delimiter="\t", columns=GKG_COLUMNS, limit=None)
    for row in rows:  # GCAM and Extras are huge; keep the profile readable
        row["GCAM"] = f"<{len(str(row.get('GCAM') or ''))} chars>"
        row["Extras"] = f"<{len(str(row.get('Extras') or ''))} chars>"
    return rows


def _latest(manifest: bytes, kind: str) -> str | None:
    """lastupdate.txt lines: '<bytes> <md5> <url>'; pick the one ending in <kind>."""
    for line in manifest.decode().splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2].endswith(kind):
            return parts[2]
    return None


def _batches(latest_url: str, count: int) -> list[str]:
    """Timestamps of the `count` most recent 15-minute batches, newest first."""
    stamp = latest_url.rsplit("/", 1)[-1][:14]
    end = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    return [(end - timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S") for i in range(count)]


def _bg_gkg(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if "#BG#" in str(r.get("Locations") or "")]


class GdeltFiles(Connector):
    ds_id = "DS-NEWS-02"
    title = "GDELT 2.0 Events and GKG raw files"
    parsers = {
        "gkg_bd.tsv": partial(parse_gdelt_gkg, columns=GKG_COLUMNS),
        "gkg_translation_bd.tsv": partial(parse_gdelt_gkg, columns=GKG_COLUMNS),
    }
    record_types = (ArticleRecord,)
    field_notes = {
        "export_latest:ActionGeo_CountryCode": FieldNote(
            "FIPS 10-4", "Where the event happened; Bangladesh is BG"
        ),
        "export_latest:EventRootCode": FieldNote("CAMEO", "Root event code (e.g. 14 protest)"),
        "export_latest:GoldsteinScale": FieldNote("-10..10", "Theoretical impact on stability"),
        "export_latest:AvgTone": FieldNote("-100..100", "Average tone of source documents"),
        "export_latest:DATEADDED": FieldNote("YYYYMMDDHHMMSS UTC", "15-minute batch timestamp"),
        "export_latest:SQLDATE": FieldNote("YYYYMMDD", "Event date as reported"),
        "gkg_latest:Locations": FieldNote("", "Type#Name#FIPS#ADM1#Lat#Long#FeatureID;…"),
        "gkg_latest:V2Themes": FieldNote("", "THEME,char-offset;… (GKG theme taxonomy)"),
        "gkg_latest:TranslationInfo": FieldNote(
            "", "srclc:<ISO 639-2>;eng:<engine>; translated stream only"
        ),
    }

    def probe(self, ctx: ProbeContext) -> None:
        manifest = ctx.http(ProbeCall("lastupdate", f"{ROOT}/lastupdate.txt", "meta"))
        translation = ctx.http(
            ProbeCall("lastupdate_translation", f"{ROOT}/lastupdate-translation.txt", "meta")
        )
        ctx.http(
            ProbeCall(
                "https_lastupdate",
                f"{ROOT.replace('http:', 'https:')}/lastupdate.txt",
                "meta",
                note="is HTTPS served?",
            )
        )
        ctx.http(
            ProbeCall(
                "masterfilelist_head",
                f"{ROOT}/masterfilelist.txt",
                "meta",
                headers={"Range": "bytes=0-4095"},
                max_bytes=4096,
                note="first 4 KiB only; the full list is large",
            )
        )
        if not manifest.ok:
            return
        export_url = _latest(manifest.body, ".export.CSV.zip")
        gkg_url = _latest(manifest.body, ".gkg.csv.zip")
        events = ctx.http(
            ProbeCall(
                "export_latest",
                export_url or "",
                decode=_events,
                records="",
                max_bytes=50_000_000,
                timeout_s=120,
            )
        )
        gkg = ctx.http(
            ProbeCall(
                "gkg_latest",
                gkg_url or "",
                decode=_gkg,
                records="",
                max_bytes=80_000_000,
                timeout_s=180,
            )
        )
        gkg_tr = None
        if translation.ok and (tr_url := _latest(translation.body, ".gkg.csv.zip")):
            gkg_tr = ctx.http(
                ProbeCall(
                    "gkg_translation_latest",
                    tr_url,
                    decode=_gkg,
                    records="",
                    max_bytes=80_000_000,
                    timeout_s=180,
                )
            )
        ctx.http(ProbeCall("missing_file", f"{ROOT}/20000101000000.export.CSV.zip", "bad_param"))
        ctx.http(ProbeCall("client_timeout", f"{ROOT}/lastupdate.txt", "timeout", timeout_s=0.001))
        self._metrics(ctx, events.parsed, gkg.parsed, gkg_tr.parsed if gkg_tr else None)
        if export_url:
            self._sweep(ctx, export_url)

    def _sweep(self, ctx: ProbeContext, export_url: str) -> None:
        """Bangladesh coverage needs more than one 15-minute batch: 24 h of events, 2 h of GKG
        (English and translated). ~120 small files, one at a time."""
        stamps = _batches(export_url, 96)
        bg_events: list[dict[str, Any]] = []
        total_events = 0
        for stamp in stamps:
            result = ctx.http(
                ProbeCall(
                    f"sweep_export_{stamp}",
                    f"{ROOT}/{stamp}.export.CSV.zip",
                    decode=_events,
                    group="export_24h",
                    note="24 h of event batches",
                )
            )
            if isinstance(result.parsed, list):
                total_events += len(result.parsed)
                bg_events += [e for e in result.parsed if e.get("ActionGeo_CountryCode") == "BG"]
            result.body, result.parsed = b"", None
        ctx.metric("sweep_events_24h", total_events)
        ctx.metric("sweep_events_24h_action_in_BG", len(bg_events))
        ctx.metric(
            "sweep_BG_event_root_codes",
            dict(Counter(str(e.get("EventRootCode")) for e in bg_events).most_common(10)),
        )
        ctx.metric(
            "sweep_BG_event_places",
            dict(Counter(str(e.get("ActionGeo_FullName")) for e in bg_events).most_common(10)),
        )
        for label, suffix in (
            ("gkg", "gkg.csv.zip"),
            ("gkg_translation", "translation.gkg.csv.zip"),
        ):
            rows_total, bg, ben = 0, [], []
            for stamp in stamps[:8]:
                result = ctx.http(
                    ProbeCall(
                        f"sweep_{label}_{stamp}",
                        f"{ROOT}/{stamp}.{suffix}",
                        decode=_gkg,
                        group=f"{label}_2h",
                        max_bytes=80_000_000,
                        timeout_s=180,
                        note="2 h of GKG batches",
                    )
                )
                if isinstance(result.parsed, list):
                    rows_total += len(result.parsed)
                    bg += _bg_gkg(result.parsed)
                    ben += [
                        r
                        for r in result.parsed
                        if "srclc:ben" in str(r.get("TranslationInfo") or "")
                    ]
                result.body, result.parsed = b"", None
            ctx.metric(f"sweep_{label}_2h_records", rows_total)
            ctx.metric(f"sweep_{label}_2h_BG_location", len(bg))
            ctx.metric(
                f"sweep_{label}_2h_BG_outlets",
                dict(Counter(str(r.get("SourceCommonName")) for r in bg).most_common(10)),
            )
            if label == "gkg_translation":
                ctx.metric("sweep_translation_2h_bengali_records", len(ben))

    @staticmethod
    def _metrics(ctx: ProbeContext, events: Any, gkg: Any, gkg_tr: Any) -> None:
        if isinstance(events, list):
            bg = [e for e in events if e.get("ActionGeo_CountryCode") == "BG"]
            ctx.metric("events_in_batch", len(events))
            ctx.metric("events_action_in_BG", len(bg))
            ctx.metric(
                "bg_event_root_codes",
                dict(Counter(str(e.get("EventRootCode")) for e in bg).most_common(10)),
            )
        for name, rows in (("gkg", gkg), ("gkg_translation", gkg_tr)):
            if not isinstance(rows, list):
                continue
            bg = [r for r in rows if "#BG#" in str(r.get("Locations") or "")]
            ctx.metric(f"{name}_records_in_batch", len(rows))
            ctx.metric(f"{name}_records_mentioning_BG_location", len(bg))
            themes: Counter[str] = Counter()
            for r in bg:
                themes.update(t for t in str(r.get("Themes") or "").split(";") if t)
            ctx.metric(f"{name}_BG_top_themes", dict(themes.most_common(12)))
            langs = Counter(str(r.get("TranslationInfo") or "").split(";")[0] for r in rows)
            if name == "gkg_translation":
                ctx.metric("translation_source_languages", dict(langs.most_common(15)))
                ben = [r for r in rows if "srclc:ben" in str(r.get("TranslationInfo") or "")]
                ctx.metric("translation_bengali_records", len(ben))
                ctx.metric(
                    "translation_bengali_outlets",
                    dict(Counter(r.get("SourceCommonName") for r in ben).most_common(10)),
                )


CONNECTOR = GdeltFiles()
