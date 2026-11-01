"""Lot inspection (C5 §6.1): ISO 2859-1 sampling with model-assisted screening.

For each finished-goods lot awaiting QC: the plan for its size and AQL; every sampled item is
defective with the lot's latent rate (simulator truth) and is shown as a real gallery image of
that kind, with the model's real score and flag on it. The model is assistive: an inspector
confirms flagged items, so confirmed defects = flagged ∧ defective, false alarms cost inspector
time, and defects the model misses go uncounted (reported as the model's cost to the buyer's
protection). Garments: accept or reject on confirmed defects. Pharma: never an automatic
decision; every lot is held for QA review with the AQL evidence.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid5

from cportal_core.enums import BatchStatus
from cportal_core.models import (
    Batch,
    InspectionImage,
    InspectionResult,
    OutboxEvent,
    Product,
)
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from cportal_c5 import MODEL_VERSION
from cportal_c5.aql import plan
from cportal_c5.config import load_config
from cportal_c5.gallery import NS


@dataclass(frozen=True)
class PoolImage:
    image_id: UUID
    uri: str
    label: str
    score: float
    flagged: bool
    threshold: float
    heatmap_uri: str | None
    model_version_id: UUID | None
    source_dataset: str
    width: int | None
    height: int | None
    dataset_id: UUID | None


@dataclass
class Pool:
    normal: list[PoolImage] = field(default_factory=list)
    defect: list[PoolImage] = field(default_factory=list)


def pools(session: Session) -> dict[str, Pool]:
    """The real gallery (replay rows) by category: normal and defective images with results."""
    rows = session.execute(
        select(InspectionImage, InspectionResult)
        .join(InspectionResult, InspectionResult.image_id == InspectionImage.id)
        .where(InspectionImage.is_synthetic.is_(False), InspectionImage.batch_id.is_(None))
    ).all()
    out: dict[str, Pool] = {}
    for img, res in rows:
        p = PoolImage(
            img.id, img.uri, img.label or "good", res.image_score, res.is_anomalous,
            res.threshold, res.heatmap_uri, res.model_version_id, img.source_dataset,
            img.width, img.height, img.dataset_id,
        )  # fmt: skip
        pool = out.setdefault(img.category, Pool())
        (pool.normal if p.label == "good" else pool.defect).append(p)
    for pool in out.values():
        pool.normal.sort(key=lambda x: x.image_id)
        pool.defect.sort(key=lambda x: x.image_id)
    return out


def _industry(sku: str) -> str:
    return "pharma" if sku.startswith("P-") else "garments"


def inspect(session: Session, scenario_id: UUID | None = None) -> dict[str, Any]:
    """Inspect every finished-goods lot still in process (idempotent: done lots are skipped)."""
    cfg = load_config()
    sku_category, aql_cfg = cfg["sku_category"], cfg["aql"]
    available = pools(session)
    q = (
        select(Batch, Product.sku)
        .join(Product, Product.id == Batch.product_id)
        .where(Batch.status == BatchStatus.IN_PROCESS.value, Batch.lot_code.like("FG-%"))
        .order_by(Batch.produced_at)
    )
    if scenario_id is not None:
        q = q.where(Batch.scenario_id == scenario_id)
    stats: Counter[str] = Counter()
    images: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for batch, sku in session.execute(q).all():
        category = sku_category.get(sku)
        pool = available.get(category) if category else None
        if pool is None or not pool.normal or not pool.defect:
            stats["skipped (no gallery for the category)"] += 1
            continue
        industry = _industry(sku)
        p = plan(batch.size_units, float(aql_cfg[industry]["major"]), aql_cfg["level"])
        rng = random.Random(batch.source_record_id or str(batch.id))  # same lot, same draw
        rate = float((batch.aql_result or {}).get("sim", {}).get("latent_defect_rate", 0.0))
        sampled: list[tuple[PoolImage, bool]] = []
        for _ in range(p.sample_size):
            defective = rng.random() < rate
            sampled.append((rng.choice(pool.defect if defective else pool.normal), defective))
        flagged = sum(img.flagged for img, _ in sampled)
        confirmed = sum(img.flagged and d for img, d in sampled)
        true_defects = sum(d for _, d in sampled)
        verdict = p.decide(confirmed)
        if industry == "pharma":
            status, decision = BatchStatus.QUARANTINE, "qa_review_required"
        else:
            status = BatchStatus.RELEASED if verdict == "accept" else BatchStatus.REJECTED
            decision = verdict
        batch.status = status.value
        batch.aql_level = f"{aql_cfg['level']} / AQL {p.aql}"  # major defects; 16 chars max
        batch.aql_result = {
            **p.as_dict(),
            "category": category,
            "items_screened": p.sample_size,
            "flagged": flagged,
            "confirmed_defects": confirmed,
            "false_alarms": flagged - confirmed,
            "aql_verdict": verdict,
            "decision": decision,
            "rule": "confirmed = items the model flagged and an inspector confirmed",
            "model_version": MODEL_VERSION,
            "inspected_at": (batch.produced_at + timedelta(hours=3)).isoformat(),
            "sim": {
                **(batch.aql_result or {}).get("sim", {}),
                "true_defects_in_sample": true_defects,
                "missed_by_model": true_defects - confirmed,
            },
        }
        stats[f"{industry}:{decision}"] += 1
        _rows(batch, category, sampled, int(aql_cfg["max_stored_items"]), images, results)
    if images:
        session.execute(insert(InspectionImage), images)
        session.execute(insert(InspectionResult), results)
        session.add(OutboxEvent(topic="inspection.completed", payload={"lots": dict(stats)}))
    return dict(stats)


def _rows(
    batch: Batch,
    category: str,
    sampled: list[tuple[PoolImage, bool]],
    cap: int,
    images: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> None:
    """Keep the confirmed defects, then false alarms, then clean items, up to `cap`."""
    order = sorted(
        range(len(sampled)),
        key=lambda i: (
            0 if sampled[i][0].flagged and sampled[i][1] else 1 if sampled[i][0].flagged else 2,
            i,
        ),
    )
    lineage = {
        "source_id": "c5",
        "data_mode": "synthetic",
        "is_synthetic": True,
        "scenario_id": batch.scenario_id,
        "generator_version": MODEL_VERSION,
    }
    for i in order[:cap]:
        img, _ = sampled[i]
        key = f"{batch.id}:{i}"
        iid = uuid5(NS, f"lot-item:{key}")
        images.append(
            {
                "id": iid, **lineage, "source_record_id": key, "dataset_id": img.dataset_id,
                "batch_id": batch.id, "product_id": batch.product_id, "category": category,
                "split": "test", "label": img.label, "uri": img.uri, "mask_uri": None,
                "width": img.width, "height": img.height, "source_dataset": img.source_dataset,
                "captured_at": batch.produced_at + timedelta(hours=3, minutes=i),
            }
        )  # fmt: skip
        results.append(
            {
                "id": uuid5(NS, f"lot-result:{key}"), **lineage, "source_record_id": key,
                "image_id": iid, "model_version_id": img.model_version_id,
                "image_score": img.score, "is_anomalous": img.flagged,
                "threshold": img.threshold, "defect_type": None, "severity": None,
                "heatmap_uri": img.heatmap_uri, "mask_uri": None, "latency_ms": None,
            }
        )  # fmt: skip
