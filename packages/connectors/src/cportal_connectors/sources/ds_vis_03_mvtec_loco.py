"""DS-VIS-03 · MVTec LOCO AD (logical anomalies; packaging analogues). CC BY-NC-SA 4.0."""

from __future__ import annotations

from cportal_connectors.base import Connector
from cportal_connectors.harness import ProbeContext
from cportal_connectors.landing import landing_and_files


class MvtecLoco(Connector):
    ds_id = "DS-VIS-03"
    title = "MVTec LOCO AD"

    def probe(self, ctx: ProbeContext) -> None:
        landing_and_files(
            ctx,
            "downloads_page",
            "https://www.mvtec.com/company/research/datasets/mvtec-loco/downloads",
            r"\.tar\.(xz|gz)$",
            max_files=2,
        )


CONNECTOR = MvtecLoco()
