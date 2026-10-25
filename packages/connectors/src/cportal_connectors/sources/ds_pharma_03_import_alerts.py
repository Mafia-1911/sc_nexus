"""DS-PHARMA-03 · FDA Import Alerts (e.g. 66-40, drug CGMP) and Warning Letters (web pages)."""

from __future__ import annotations

import re

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.decoders import text_of
from cportal_connectors.harness import ProbeContext

ACCESSDATA = "https://www.accessdata.fda.gov"


class ImportAlerts(Connector):
    ds_id = "DS-PHARMA-03"
    title = "FDA Import Alerts and Warning Letters"

    def probe(self, ctx: ProbeContext) -> None:
        robots = ctx.http(ProbeCall("accessdata_robots", f"{ACCESSDATA}/robots.txt", "meta"))
        alert = ctx.http(
            ProbeCall(
                "import_alert_66_40",
                f"{ACCESSDATA}/cms_ia/importalert_189.html",
                sample=True,
                timeout_s=60,
                note="66-40: drugs from firms not meeting CGMP",
            )
        )
        text = " ".join(text_of(alert.body).split())
        ctx.metric(
            "alert_66_40_firm_rows_mentioning",
            {
                country: len(re.findall(country, text, re.I))
                for country in ("India", "China", "Bangladesh")
            },
        )
        ctx.metric(
            "robots_disallow_cms_ia",
            [
                line.strip()
                for line in robots.body.decode("utf-8", "replace").splitlines()
                if "cms_ia" in line or "Crawl" in line
            ][:10],
        )


CONNECTOR = ImportAlerts()
