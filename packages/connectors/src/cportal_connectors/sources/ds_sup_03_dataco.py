"""DS-SUP-03 · DataCo Smart Supply Chain: orders with a late-delivery label (Mendeley Data)."""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.decoders import html_outline
from cportal_connectors.harness import ProbeContext

PAGE = "https://data.mendeley.com/datasets/8gx2fvg2k6/5"
PUBLIC_API = "https://data.mendeley.com/public-api/datasets/8gx2fvg2k6"


class DataCo(Connector):
    ds_id = "DS-SUP-03"
    title = "DataCo Smart Supply Chain"

    def probe(self, ctx: ProbeContext) -> None:
        page = ctx.http(ProbeCall("mendeley_page", PAGE, "meta", decode=html_outline))
        ctx.metric(
            "page_title",
            (page.parsed or {}).get("title") if isinstance(page.parsed, dict) else None,
        )
        meta = ctx.http(
            ProbeCall("public_api_dataset", PUBLIC_API, sample=True, params={"version": 5})
        )
        ctx.http(
            ProbeCall(
                "public_api_files",
                f"{PUBLIC_API}/files",
                "meta",
                params={"folder_id": "root", "version": 5},
            )
        )
        if isinstance(meta.parsed, dict):
            ctx.metric(
                "dataset",
                {
                    k: meta.parsed.get(k)
                    for k in ("name", "version", "publish_date", "data_licence", "doi")
                },
            )


CONNECTOR = DataCo()
