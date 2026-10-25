"""DS-VIS-01 · MVTec AD (pill, capsule, carpet, leather): CC BY-NC-SA 4.0, no commercial use."""

from __future__ import annotations

import re

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.decoders import text_of
from cportal_connectors.harness import ProbeContext
from cportal_connectors.vision import archive_head

PAGE = "https://www.mvtec.com/company/research/datasets/mvtec-ad"
DOWNLOADS = f"{PAGE}/downloads"
# Direct links as listed on the downloads page (read 2026-10-26).
ARCHIVES = {
    "pill": "https://www.mydrive.ch/shares/150460/d4f1c04da67034ccc8d8b5fa3e73f244/download/420938129-1629960351/pill.tar.xz",
    "capsule": "https://www.mydrive.ch/shares/150454/e0ce6dd74eb150f46c0d98131b3703f2/download/420937454-1629958872/capsule.tar.xz",
    "carpet": "https://www.mydrive.ch/shares/150455/eac7fbce84d93a5094e13f391170eca4/download/420937484-1629959013/carpet.tar.xz",
    "leather": "https://www.mydrive.ch/shares/150458/923030ce14e10a7d147e95d0f8885f6b/download/420937607-1629959262/leather.tar.xz",
    "full": "https://www.mydrive.ch/shares/150996/b52ecdcbf521176e9db9c731f2304b27/download/420938113-1629960298/mvtec_anomaly_detection.tar.xz",
}


class MvtecAd(Connector):
    ds_id = "DS-VIS-01"
    title = "MVTec AD"

    def probe(self, ctx: ProbeContext) -> None:
        page = ctx.http(ProbeCall("dataset_page", PAGE, "meta"))
        ctx.http(ProbeCall("downloads_page", DOWNLOADS, "meta"))
        for category, url in ARCHIVES.items():
            archive_head(ctx, f"archive_{category}", url)
        ctx.http(
            ProbeCall(
                "missing_share",
                "https://www.mydrive.ch/shares/1/0/download/0-0/x.tar.xz",
                "bad_param",
                max_bytes=4096,
            )
        )
        ctx.http(ProbeCall("client_timeout", PAGE, "timeout", timeout_s=0.001))
        text = " ".join(text_of(page.body).split())
        match = re.search(r"Creative Commons[^.<]{0,120}", text)
        ctx.metric("licence_statement", match.group(0) if match else None)
        ctx.metric(
            "commercial_use_forbidden",
            "not allowed to use the dataset for commercial purposes" in text,
        )


CONNECTOR = MvtecAd()
