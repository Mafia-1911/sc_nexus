"""DS-NEWS-04 · ReliefWeb API v2: needs a pre-approved `appname` since 1 Nov 2025."""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext

API = "https://api.reliefweb.int/v2/reports"


class ReliefWeb(Connector):
    ds_id = "DS-NEWS-04"
    title = "ReliefWeb API v2"
    needs = ("RELIEFWEB_APPNAME",)

    def probe(self, ctx: ProbeContext) -> None:
        params = {"query[value]": "Bangladesh cyclone", "limit": 5, "sort[]": "date:desc"}
        ctx.http(ProbeCall("no_appname", API, "no_key", params=params))
        ctx.http(
            ProbeCall(
                "unapproved_appname",
                API,
                "bad_key",
                params={**params, "appname": "cportal-unapproved-probe"},
            )
        )
        if appname := ctx.settings.reliefweb_appname:
            ctx.http(
                ProbeCall(
                    "reports_bgd",
                    API,
                    sample=True,
                    records="data[]",
                    params={**params, "appname": appname},
                )
            )


CONNECTOR = ReliefWeb()
