"""DS-VIS-02 · VisA (Amazon spot-diff): 12 categories incl. capsules; CC BY 4.0."""

from __future__ import annotations

from collections import Counter
from typing import Any

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.decoders import csv_decoder
from cportal_connectors.harness import ProbeContext
from cportal_connectors.vision import archive_head

TAR = "https://amazon-visual-anomaly.s3.us-west-2.amazonaws.com/VisA_20220922.tar"
RAW = "https://raw.githubusercontent.com/amazon-science/spot-diff/main"


class Visa(Connector):
    ds_id = "DS-VIS-02"
    title = "VisA"
    field_notes = {
        "split_1cls:object": FieldNote("", "Category folder, e.g. capsules"),
        "split_1cls:split": FieldNote("", "train / test"),
        "split_1cls:label": FieldNote("", "normal / anomaly"),
        "split_1cls:mask": FieldNote("", "Path of the pixel mask (anomalies only)"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(ProbeCall("readme", f"{RAW}/README.md", "meta"))
        licence = ctx.http(ProbeCall("license_dataset", f"{RAW}/LICENSE-DATASET", "meta"))
        archive_head(ctx, "archive", TAR)
        split = ctx.http(
            ProbeCall(
                "split_1cls",
                f"{RAW}/split_csv/1cls.csv",
                sample=True,
                decode=csv_decoder(limit=None),
                records="",
            )
        )
        ctx.http(
            ProbeCall(
                "missing_key",
                TAR.replace("VisA_20220922", "VisA_19990101"),
                "bad_param",
                max_bytes=4096,
            )
        )
        ctx.metric(
            "licence_first_line",
            licence.body[:120].decode("utf-8", "replace").strip() if licence.body else None,
        )
        rows: Any = split.parsed
        if isinstance(rows, list):
            ctx.metric("split_rows", len(rows))
            ctx.metric(
                "capsules_by_split_label",
                dict(
                    Counter(
                        f"{r.get('split')}/{r.get('label')}"
                        for r in rows
                        if r.get("object") == "capsules"
                    )
                ),
            )
            ctx.metric("objects", sorted({str(r.get("object")) for r in rows}))


CONNECTOR = Visa()
