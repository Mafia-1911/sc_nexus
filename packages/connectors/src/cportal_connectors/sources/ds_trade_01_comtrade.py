"""DS-TRADE-01 · UN Comtrade API: Bangladesh import dependencies by HS code and partner."""

from __future__ import annotations

from typing import Any

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext

DATA = "https://comtradeapi.un.org/data/v1"
PUBLIC = "https://comtradeapi.un.org/public/v1"
FILES = "https://comtradeapi.un.org/files/v1/app/reference"
# Garment inputs: cotton 52, man-made filament 54, staple fibre 55, knitted fabric 60.
# Pharma inputs: heterocyclic compounds 2933, antibiotics 2941, medicaments 3004.
GARMENT = "52,54,55,60"
PHARMA = "2933,2941,3004"


class Comtrade(Connector):
    ds_id = "DS-TRADE-01"
    title = "UN Comtrade API"
    needs = ("COMTRADE_API_KEY",)
    field_notes = {
        "bgd_imports_garment_inputs:primaryValue": FieldNote("US$", "Trade value"),
        "bgd_imports_garment_inputs:netWgt": FieldNote("kg", "Net weight (often null)"),
        "bgd_imports_garment_inputs:partnerCode": FieldNote("M49", "Partner country code"),
        "bgd_imports_garment_inputs:cmdCode": FieldNote("HS", "Commodity code"),
        "bgd_imports_garment_inputs:period": FieldNote("year", "Reference year"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        key = ctx.secret("COMTRADE_API_KEY")
        auth = {"Ocp-Apim-Subscription-Key": key} if key else {}
        ctx.http(ProbeCall("reporters_reference", f"{FILES}/Reporters.json", "meta"))
        ctx.http(
            ProbeCall(
                "preview_no_key",
                f"{PUBLIC}/preview/C/A/HS",
                "no_key",
                params={"reporterCode": 50, "period": 2023, "cmdCode": 52, "flowCode": "M"},
                note="keyless preview endpoint (≤ 500 records)",
            )
        )
        ctx.http(
            ProbeCall(
                "bad_key",
                f"{DATA}/get/C/A/HS",
                "bad_key",
                headers={"Ocp-Apim-Subscription-Key": "0" * 32},
                params={"reporterCode": 50, "period": 2023, "cmdCode": 52, "flowCode": "M"},
            )
        )
        if not key:
            return
        avail = ctx.http(
            ProbeCall(
                "availability_bgd",
                f"{DATA}/getDA/C/A/HS",
                "meta",
                headers=auth,
                params={"reporterCode": 50},
                note="which years Bangladesh itself reported",
            )
        )
        own = ctx.http(
            ProbeCall(
                "bgd_imports_garment_inputs",
                f"{DATA}/get/C/A/HS",
                headers=auth,
                sample=True,
                records="data[]",
                params={
                    "reporterCode": 50,
                    "period": "2022,2023,2024",
                    "cmdCode": GARMENT,
                    "flowCode": "M",
                    "partnerCode": "",
                    "includeDesc": "true",
                },
                note="Bangladesh-reported imports of garment inputs",
            )
        )
        mirror = ctx.http(
            ProbeCall(
                "mirror_cn_in_exports_to_bgd",
                f"{DATA}/get/C/A/HS",
                headers=auth,
                sample=True,
                records="data[]",
                params={
                    "reporterCode": "156,699",
                    "partnerCode": 50,
                    "period": "2024",
                    "cmdCode": f"{GARMENT},{PHARMA}",
                    "flowCode": "X",
                    "includeDesc": "true",
                },
                note="mirror data: China and India report exports to Bangladesh",
            )
        )
        ctx.http(
            ProbeCall(
                "bad_commodity",
                f"{DATA}/get/C/A/HS",
                "bad_param",
                headers=auth,
                params={"reporterCode": 50, "period": 2023, "cmdCode": "XX", "flowCode": "M"},
            )
        )
        ctx.http(
            ProbeCall(
                "client_timeout",
                f"{DATA}/get/C/A/HS",
                "timeout",
                headers=auth,
                params={"reporterCode": 50, "period": 2023, "cmdCode": 52, "flowCode": "M"},
                timeout_s=0.001,
            )
        )
        ctx.metric(
            "bgd_reported_periods", sorted({str(r.get("period")) for r in self._rows(avail.parsed)})
        )
        for name, result in (("own", own), ("mirror", mirror)):
            rows = self._rows(result.parsed)
            ctx.metric(f"{name}_rows", len(rows))
            value_musd: dict[str, float] = {}
            for r in rows:
                flow = f"{r.get('reporterDesc')}→{r.get('partnerDesc')} {r.get('cmdCode')}"
                value_musd[flow] = (
                    value_musd.get(flow, 0.0) + float(r.get("primaryValue") or 0) / 1e6
                )
            top = sorted(value_musd.items(), key=lambda kv: -kv[1])[:10]
            ctx.metric(f"{name}_top_flows_musd", {k: round(v, 1) for k, v in top})

    @staticmethod
    def _rows(doc: Any) -> list[dict[str, Any]]:
        data = doc.get("data") if isinstance(doc, dict) else None
        return data if isinstance(data, list) else []


CONNECTOR = Comtrade()
