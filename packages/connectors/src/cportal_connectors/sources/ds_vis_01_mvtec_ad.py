"""DS-VIS-01 · MVTec AD (pill, capsule, carpet, leather): CC BY-NC-SA 4.0, no commercial use.

The official mydrive.ch archive links returned 404 in M0 (two strikes, not retried). At G0 the
user confirmed the download page is broken and pointed to Kaggle mirrors; this probe reads the
licence from the official page and lists the mirrors through the Kaggle API. A mirror's own
licence label does not override MVTec's CC BY-NC-SA 4.0.
"""

from __future__ import annotations

import re

from cportal_connectors import kaggle
from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.decoders import text_of
from cportal_connectors.harness import ProbeContext

PAGE = "https://www.mvtec.com/company/research/datasets/mvtec-ad"
# The full release is ~4.9 GB: 15 categories, 5,354 images.
FULL_SIZE_BYTES = 4_000_000_000


class MvtecAd(Connector):
    ds_id = "DS-VIS-01"
    title = "MVTec AD"
    needs = ("KAGGLE_API_TOKEN",)

    def probe(self, ctx: ProbeContext) -> None:
        page = ctx.http(ProbeCall("dataset_page", PAGE, "meta"))
        text = " ".join(text_of(page.body).split())
        match = re.search(r"Creative Commons[^.<]{0,120}", text)
        ctx.metric("licence_statement", match.group(0) if match else None)
        ctx.metric(
            "commercial_use_forbidden",
            "not allowed to use the dataset for commercial purposes" in text,
        )
        kaggle.search(ctx, "kaggle_no_token", "mvtec ad", purpose="no_key")
        if not ctx.has("KAGGLE_API_TOKEN"):
            return
        found = kaggle.search(ctx, "kaggle_search_mvtec_ad", "mvtec ad")
        mirrors = kaggle.summarise(found.parsed)
        ctx.metric("kaggle_mirrors", mirrors)
        full = [
            m
            for m in mirrors
            if "loco" not in str(m["ref"]).lower() and (m.get("totalBytes") or 0) >= FULL_SIZE_BYTES
        ]
        if full:
            ctx.metric("kaggle_mirror_chosen", full[0]["ref"])
            listing = kaggle.files(ctx, "kaggle_mirror_files", str(full[0]["ref"]))
            names = [
                f.get("name")
                for f in ((listing.parsed or {}).get("datasetFiles") or [])
                if isinstance(f, dict)
            ]
            ctx.metric("kaggle_mirror_first_files", names[:20])


CONNECTOR = MvtecAd()
