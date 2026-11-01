"""C5 public API (02 §6): reads for the Quality Lab, plus live inspection of one uploaded image.

Everything but `Live.inspect` is a database read. The live path runs the ONNX encoder and the
category's few-shot bank (≈ 0.4 s on CPU, C5-AC02); heavy evaluation never runs in a request.
"""

from __future__ import annotations

import io
import threading
import time
from datetime import timedelta
from typing import Any, ClassVar
from uuid import UUID, uuid4

import numpy as np
from cportal_core.models import (
    Alert,
    Batch,
    CustomerOrder,
    Facility,
    InspectionImage,
    InspectionResult,
    ModelVersion,
    Organization,
    Prediction,
    Product,
    Recommendation,
)
from PIL import Image
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from cportal_c5 import risk
from cportal_c5.config import ARTIFACTS, MODELS, load_config
from cportal_c5.gallery import load_bank, overlay
from cportal_c5.schemas import (
    ItemOut,
    LineOut,
    LiveResultOut,
    LotDetailOut,
    LotOptionOut,
    LotOut,
    SpcOut,
)
from cportal_c5.store import line_id, plant_label
from cportal_c5.vision import Encoder, _nearest_distance, _stitch, image_score

MAX_UPLOAD = 10 * 1024 * 1024


def _lot_query(scenario_id: UUID | None) -> Any:
    risk_pred = (
        select(Prediction.target_id, Prediction.value)
        .where(Prediction.capability == "c5", Prediction.target_type == "batch")
        .subquery()
    )
    q = (
        select(Batch, Product, Facility, CustomerOrder, risk_pred.c.value, Alert.id, Organization)
        .join(Product, Product.id == Batch.product_id)
        .join(Facility, Facility.id == Batch.facility_id)
        .join(Organization, Organization.id == Facility.organization_id)
        .outerjoin(CustomerOrder, CustomerOrder.id == Batch.order_id)
        .outerjoin(risk_pred, risk_pred.c.target_id == Batch.id)
        .outerjoin(Alert, Alert.dedupe_key == func.concat("c5:lot:", Batch.id))
        .where(Batch.lot_code.like("FG-%"))
    )
    if scenario_id is not None:
        q = q.where(Batch.scenario_id == scenario_id)
    return q


def _lot(row: Any) -> LotOut:
    b, p, f, o, risk_before, alert_id, org = row
    r = b.aql_result or {}
    return LotOut(
        id=b.id, lot_code=b.lot_code, sku=p.sku, product=p.name,
        industry="pharma" if p.sku.startswith("P-") else "garments",
        category=load_config()["sku_category"].get(p.sku), facility_id=f.id,
        facility=plant_label(org, f), cluster=f.cluster,
        line=b.line, shift=b.shift, size_units=b.size_units, produced_at=b.produced_at,
        status=b.status, decision=r.get("decision"), sample_size=r.get("sample_size"),
        accept=r.get("accept"), confirmed_defects=r.get("confirmed_defects"),
        flagged=r.get("flagged"), false_alarms=r.get("false_alarms"), risk_before=risk_before,
        order_ref=o.reference if o else None, order_due=o.due_date if o else None,
        alert_id=alert_id,
    )  # fmt: skip


def lots(
    session: Session,
    scenario_id: UUID | None,
    status: str | None = None,
    industry: str | None = None,
    days: int = 21,
    limit: int = 300,
) -> list[LotOut]:
    """The batch board: lots inspected in the last `days` of the scenario clock, newest first."""
    q = _lot_query(scenario_id)
    newest = session.scalar(
        select(func.max(Batch.produced_at)).where(
            Batch.lot_code.like("FG-%"), Batch.scenario_id == scenario_id
        )
    )
    if newest is not None:
        q = q.where(Batch.produced_at >= newest - timedelta(days=days))
    if status:
        q = q.where(Batch.status == status)
    if industry:
        q = q.where(Product.sku.like("P-%" if industry == "pharma" else "G-%"))
    rows = session.execute(q.order_by(Batch.produced_at.desc()).limit(limit)).all()
    return [_lot(r) for r in rows]


def _items(session: Session, where: Any, limit: int) -> list[ItemOut]:
    rows = session.execute(
        select(InspectionImage, InspectionResult)
        .join(InspectionResult, InspectionResult.image_id == InspectionImage.id)
        .where(where)
        .order_by(InspectionResult.is_anomalous.desc(), InspectionResult.image_score.desc())
        .limit(limit)
    ).all()
    return [
        ItemOut(
            id=img.id,
            category=img.category,
            label=img.label,
            image_url=img.uri,
            heatmap_url=res.heatmap_uri,
            score=round(res.image_score, 5),
            threshold=round(res.threshold, 5),
            flagged=res.is_anomalous,
            source_dataset=img.source_dataset,
        )
        for img, res in rows
    ]


def lot(session: Session, scenario_id: UUID | None, lot_id: UUID) -> LotDetailOut | None:
    row = session.execute(_lot_query(scenario_id).where(Batch.id == lot_id)).first()
    if row is None:
        return None
    out = _lot(row)
    batch, order = row[0], row[3]
    alert = session.get(Alert, out.alert_id) if out.alert_id else None
    recs = (
        session.scalars(
            select(Recommendation)
            .where(Recommendation.alert_id == alert.id)
            .order_by(Recommendation.id)
        ).all()
        if alert
        else []
    )
    line = next(
        (
            x
            for x in lines(session, scenario_id)
            if x.facility_id == batch.facility_id and x.line == batch.line
        ),
        None,
    )
    aql = {k: v for k, v in (batch.aql_result or {}).items() if k != "sim"}
    sim = (batch.aql_result or {}).get("sim", {})
    aql["simulation"] = {  # simulator truth, shown as such (SYNTHETIC)
        "true_defects_in_sample": sim.get("true_defects_in_sample"),
        "missed_by_model": sim.get("missed_by_model"),
    }
    order_out = None
    if order is not None:
        order_out = {
            "reference": order.reference,
            "due_date": order.due_date.isoformat(),
            "qty": order.qty,
            "revenue_usd": order.revenue_usd,
            "status": order.status,
        }
    alert_out = None
    if alert is not None:
        alert_out = {
            "id": str(alert.id),
            "title": alert.title,
            "body": alert.body,
            "severity": alert.severity,
            "status": alert.status,
        }
    return LotDetailOut(
        lot=out,
        aql=aql,
        items=_items(session, InspectionImage.batch_id == lot_id, 24),
        order=order_out,
        alert=alert_out,
        recommendations=[
            LotOptionOut(
                id=r.id,
                action_type=r.action_type,
                expected_cost_usd=r.expected_cost_usd,
                expected_benefit_usd=r.expected_benefit_usd,
                confidence=r.confidence,
                rationale=r.rationale,
                params=r.params,
                status=r.status,
            )
            for r in sorted(
                recs,
                key=lambda r: -((r.expected_benefit_usd or 0) - (r.expected_cost_usd or 0)),
            )
        ],
        line=line.model_dump(mode="json") if line else None,
    )


def lines(session: Session, scenario_id: UUID | None) -> list[LineOut]:
    rows = session.execute(
        select(Prediction, Facility, Organization)
        .join(
            Facility,
            Facility.id
            == func.cast(Prediction.explanation["facility_id"].astext, Facility.id.type),
        )
        .join(Organization, Organization.id == Facility.organization_id)
        .where(
            Prediction.capability == "c5",
            Prediction.target_type == "line",
            Prediction.scenario_id == scenario_id,
        )
        .order_by(Prediction.value.desc())
    ).all()
    return [
        LineOut(
            id=p.target_id,
            facility_id=UUID(p.explanation["facility_id"]),
            facility=plant_label(org, fac),
            line=p.explanation["line"],
            industry=p.explanation["industry"],
            p_fail_next=float(p.value or 0),
            rate=float(p.explanation["rate"]),
            alarm_now=bool(p.explanation["alarm_now"]),
            alarms=int(p.explanation["alarms"]),
        )
        for p, fac, org in rows
    ]


def spc(session: Session, scenario_id: UUID | None, line: UUID) -> SpcOut | None:
    history = risk.load_lots(session, scenario_id)
    charts = risk.spc(history)
    key = next((k for k in charts if line_id(k) == line), None)
    if key is None:
        return None
    chart = charts[key]
    meta = next((x for x in lines(session, scenario_id) if x.id == line), None)
    return SpcOut(
        line=meta, center=chart["center"], ewma_ucl=chart["ewma_ucl"], points=chart["points"]
    )


def gallery(session: Session, category: str | None, limit: int = 48) -> list[ItemOut]:
    where = and_(InspectionImage.is_synthetic.is_(False), InspectionImage.batch_id.is_(None))
    if category:
        where = and_(where, InspectionImage.category == category)
    return _items(session, where, limit)


def summary(session: Session, scenario_id: UUID | None) -> dict[str, Any]:
    board = lots(session, scenario_id, limit=2000)
    line_rows = lines(session, scenario_id)
    models = session.scalars(
        select(ModelVersion).where(
            ModelVersion.capability == "c5", ModelVersion.is_synthetic.is_(False)
        )
    ).all()
    risk_model = session.scalar(
        select(ModelVersion).where(
            ModelVersion.capability == "c5", ModelVersion.scenario_id == scenario_id
        )
    )
    return {
        "lots": len(board),
        "rejected": sum(1 for x in board if x.status == "rejected"),
        "held_for_qa": sum(1 for x in board if x.status == "quarantine"),
        "orders_at_risk": len({x.order_ref for x in board if x.alert_id and x.order_ref}),
        "lines_alarming": sum(1 for x in line_rows if x.alarm_now),
        "categories": {
            m.name.split("(")[-1].rstrip(")"): {
                "method": m.card.get("method"),
                "threshold": m.card.get("threshold"),
                "licence": m.card.get("data_licence"),
                "metrics": (m.metrics or {}).get("methods", {}).get(m.card.get("method", ""), {}),
                "encode_ms": (m.metrics or {}).get("encode_ms_per_image"),
            }
            for m in models
        },
        "lot_risk": (risk_model.metrics if risk_model else {}),
    }


class Live:
    """Few-shot scoring of one uploaded image with the category's bank (lazy, per process)."""

    _lock = threading.Lock()
    _encoder: Encoder | None = None
    _banks: ClassVar[dict[str, tuple[np.ndarray, dict[str, Any]]]] = {}

    @classmethod
    def categories(cls) -> list[str]:
        return sorted(p.stem for p in MODELS.glob("*.npz"))

    @classmethod
    def inspect(cls, data: bytes, category: str) -> LiveResultOut:
        if len(data) > MAX_UPLOAD:
            raise ValueError("image larger than 10 MB")
        if category not in cls.categories():
            raise LookupError(f"no few-shot bank for {category!r}; known: {cls.categories()}")
        try:
            Image.open(io.BytesIO(data)).verify()
            img = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception as exc:  # not an image Pillow can read
            raise ValueError(f"not a readable image ({type(exc).__name__})") from exc
        with cls._lock:
            if cls._encoder is None:
                cls._encoder = Encoder(side=int(load_config()["vision"]["side"]))
            if category not in cls._banks:
                cls._banks[category] = load_bank(category)
            encoder, (bank, meta) = cls._encoder, cls._banks[category]
        t0 = time.perf_counter()
        feats = encoder.features(img, tile=meta.get("tile"))
        maps = [_nearest_distance(tile, bank) for tile in feats.patches]
        score = image_score(np.concatenate(maps))
        heat = _stitch(feats, maps)
        ms = (time.perf_counter() - t0) * 1000
        uid = uuid4()
        out_dir = ARTIFACTS / "uploads"
        out_dir.mkdir(parents=True, exist_ok=True)
        thumb = img.copy()
        thumb.thumbnail((384, 384))
        thumb.save(out_dir / f"{uid}.jpg", quality=85)
        threshold = float(meta["threshold"])
        overlay(heat, threshold, thumb.size).save(out_dir / f"{uid}_heat.png")
        return LiveResultOut(
            category=category, score=round(score, 5), threshold=round(threshold, 5),
            flagged=score > threshold, image_url=f"uploads/{uid}.jpg",
            heatmap_url=f"uploads/{uid}_heat.png", latency_ms=round(ms, 1), method=meta["method"],
        )  # fmt: skip
