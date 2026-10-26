"""DS-PHARMA-01 · openFDA: drug recalls (enforcement reports) and drug shortages."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cportal_core.schemas.records import DisruptionEventRecord

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext
from cportal_connectors.parsers.hazards import parse_openfda_recalls, parse_openfda_shortages

BASE = "https://api.fda.gov"


class OpenFda(Connector):
    ds_id = "DS-PHARMA-01"
    title = "openFDA drug enforcement and shortages"
    parsers = {
        "recalls_india.json": parse_openfda_recalls,
        "shortages.json": parse_openfda_shortages,
    }
    record_types = (DisruptionEventRecord,)
    needs = ()  # OPENFDA_API_KEY is optional: 1,000 requests/day per IP without it
    field_notes = {
        "recalls_india:recall_number": FieldNote("", "FDA recall number (unique per product)"),
        "recalls_india:classification": FieldNote("", "Class I (most serious) / II / III"),
        "recalls_india:report_date": FieldNote("YYYYMMDD", "Date FDA published the report"),
        "recalls_india:recall_initiation_date": FieldNote("YYYYMMDD", "Firm started the recall"),
        "recalls_india:country": FieldNote("", "Country of the recalling firm"),
        "recalls_india:reason_for_recall": FieldNote("", "Free text, e.g. CGMP deviations"),
        "recalls_india:openfda": FieldNote("", "Harmonised fields; often empty for recalls"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        key = {"api_key": ctx.secret("OPENFDA_API_KEY")} if ctx.has("OPENFDA_API_KEY") else {}
        this_year = datetime.now(UTC).year
        window = f"[{this_year - 1}0101 TO {this_year}1231]"
        recalls = ctx.http(
            ProbeCall(
                "recalls_india",
                f"{BASE}/drug/enforcement.json",
                sample=True,
                records="results[]",
                params={
                    **key,
                    "search": f'country:"India" AND report_date:{window}',
                    "limit": 100,
                    "sort": "report_date:desc",
                },
                note="drug recalls by firms in India, last two calendar years",
            )
        )
        ctx.http(
            ProbeCall(
                "recalls_by_country",
                f"{BASE}/drug/enforcement.json",
                "meta",
                params={**key, "search": f"report_date:{window}", "count": "country.exact"},
                note="which countries' firms recall drugs in the US",
            )
        )
        ctx.http(
            ProbeCall(
                "recalls_bangladesh",
                f"{BASE}/drug/enforcement.json",
                sample=True,
                records="results[]",
                params={**key, "search": 'country:"Bangladesh"', "limit": 100},
            )
        )
        shortages = ctx.http(
            ProbeCall(
                "shortages",
                f"{BASE}/drug/shortages.json",
                sample=True,
                records="results[]",
                params={**key, "limit": 100},
                note="the brief's first candidate path",
            )
        )
        if not shortages.ok:
            ctx.http(
                ProbeCall(
                    "drugshortages",
                    f"{BASE}/drug/drugshortages.json",
                    sample=True,
                    records="results[]",
                    params={**key, "limit": 100},
                    note="the brief's second candidate path",
                )
            )
        ctx.http(
            ProbeCall(
                "no_match",
                f"{BASE}/drug/enforcement.json",
                "empty",
                params={**key, "search": 'country:"Atlantis"'},
            )
        )
        ctx.http(
            ProbeCall(
                "limit_over_max",
                f"{BASE}/drug/enforcement.json",
                "oversized",
                params={**key, "limit": 1001},
                note="documented max limit is 1000",
            )
        )
        ctx.http(
            ProbeCall(
                "skip_over_max",
                f"{BASE}/drug/enforcement.json",
                "last_page",
                params={**key, "limit": 1, "skip": 25001},
                note="documented max skip is 25000",
            )
        )
        ctx.http(
            ProbeCall(
                "bad_field",
                f"{BASE}/drug/enforcement.json",
                "bad_param",
                params={**key, "search": "no_such_field:x"},
            )
        )
        ctx.http(
            ProbeCall(
                "bad_key",
                f"{BASE}/drug/enforcement.json",
                "bad_key",
                params={"api_key": "not-a-real-key", "limit": 1},
            )
        )
        ctx.http(
            ProbeCall(
                "client_timeout",
                f"{BASE}/drug/enforcement.json",
                "timeout",
                params={**key, "limit": 1},
                timeout_s=0.001,
            )
        )
        self._metrics(ctx, recalls.parsed)

    @staticmethod
    def _metrics(ctx: ProbeContext, doc: Any) -> None:
        if not isinstance(doc, dict):
            return
        ctx.metric("recalls_india_meta", doc.get("meta", {}).get("results"))
        ctx.metric("recalls_india_last_updated", doc.get("meta", {}).get("last_updated"))
        classes: dict[str, int] = {}
        for rec in doc.get("results", []):
            classes[rec.get("classification", "?")] = (
                classes.get(rec.get("classification", "?"), 0) + 1
            )
        ctx.metric("recalls_india_by_class", classes)


CONNECTOR = OpenFda()
