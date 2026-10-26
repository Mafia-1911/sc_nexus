"""Image dataset provenance (Kaggle, VisA, Roboflow) and image lists for C5."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from typing import Any

from cportal_core.enums import ImageSplit
from cportal_core.schemas.records import ImageDatasetRecord, InspectionImageRecord, Record

from cportal_connectors.canonical import ParseContext

# MVTec AD's 15 categories (Bergmann et al., CVPR 2019; the mirror keeps the original layout).
MVTEC_AD_CATEGORIES = [
    "bottle", "cable", "capsule", "carpet", "grid", "hazelnut", "leather", "metal_nut",
    "pill", "screw", "tile", "toothbrush", "transistor", "wood", "zipper",
]  # fmt: skip
MVTEC_LICENCE = "CC BY-NC-SA 4.0 (MVTec; the mirror's label does not change it)"


def _kaggle_field(d: dict[str, Any], name: str) -> Any:
    """The Kaggle v1 API returns `title` or `titleNullable` depending on the endpoint."""
    return d.get(name, d.get(f"{name}Nullable"))


def parse_kaggle_mvtec(body: bytes, ctx: ParseContext) -> list[Record]:
    """Search results → the chosen MVTec AD mirror as an image dataset (A-026)."""
    for d in json.loads(body):
        slug = str(_kaggle_field(d, "url") or "").rsplit("/", 1)[-1]
        ref = _kaggle_field(d, "ref") or f"{_kaggle_field(d, 'ownerRef')}/{slug}"
        if ref != "ipythonx/mvtec-ad":
            continue
        return [
            ImageDatasetRecord(
                id=ctx.rid("image_dataset", ref),
                **ctx.lineage(ref),
                dataset_ref=f"kaggle:{ref}",
                title="MVTec AD (Kaggle mirror)",
                licence=MVTEC_LICENCE,
                nc=True,
                url=_kaggle_field(d, "url"),
                task="anomaly_detection",
                categories=MVTEC_AD_CATEGORIES,
                classes=["good", "defect"],
                size_bytes=_kaggle_field(d, "totalBytes"),
            )
        ]
    return []


def parse_visa_split(body: bytes, ctx: ParseContext) -> list[Record]:
    """VisA `split_csv/1cls.csv`: object,split,label,image,mask → dataset + one row per image."""
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8"))))
    dataset_id = ctx.rid("image_dataset", "visa")
    splits = Counter(r["split"] for r in rows)
    out: list[Record] = [
        ImageDatasetRecord(
            id=dataset_id,
            **ctx.lineage("visa"),
            dataset_ref="github:amazon-science/spot-diff",
            title="VisA (Visual Anomaly)",
            licence="CC BY 4.0",
            nc=False,
            url="https://github.com/amazon-science/spot-diff",
            task="anomaly_detection",
            categories=sorted({r["object"] for r in rows}),
            classes=sorted({r["label"] for r in rows}),
            n_images=len(rows),
            splits=dict(splits),
        )
    ]
    for r in rows:
        out.append(
            InspectionImageRecord(
                id=ctx.rid("inspection_image", f"visa:{r['image']}"),
                **ctx.lineage(r["image"]),
                dataset_id=dataset_id,
                category=r["object"],
                split=ImageSplit(r["split"])
                if r["split"] in ImageSplit._value2member_map_
                else None,
                label=r["label"],
                uri=f"visa://{r['image']}",
                mask_uri=f"visa://{r['mask']}" if r.get("mask") else None,
                source_dataset="VisA",
            )
        )
    return out


def parse_roboflow_project(body: bytes, ctx: ParseContext) -> list[Record]:
    doc = json.loads(body)
    project = doc.get("project") or {}
    ref = project.get("id")
    if not ref:
        return []
    splits = project.get("splits") or {}
    return [
        ImageDatasetRecord(
            id=ctx.rid("image_dataset", ref),
            **ctx.lineage(ref),
            dataset_ref=f"roboflow:{ref}",
            title=project.get("name") or ref,
            licence=project.get("license"),
            nc="NC" in str(project.get("license") or ""),
            url=f"https://universe.roboflow.com/{ref}",
            task=str(project.get("type") or "object-detection").replace("-", "_"),
            classes=sorted((project.get("classes") or {}).keys()),
            n_images=project.get("images"),
            splits={
                k: int(v)
                for k, v in splits.items()
                if k in ("train", "valid", "test") and str(v).isdigit()
            },
        )
    ]
