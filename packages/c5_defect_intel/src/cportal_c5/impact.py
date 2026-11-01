"""From a failed lot to orders at risk and costed options (C5 §6.4, C5-AC06).

A rejected garment lot (or a pharma lot whose confirmed defects exceed its AQL limit) blocks the
order it was made for. The order is at risk when it now depends on rework succeeding: remaking the
lot would finish after the order must be ready (two days before its due date). Each such lot
raises one alert with recommendations, every one with an expected cost and benefit in USD: rework,
replacement production, air freight when remaking misses the sea cut-off, and telling the buyer.
Pharma: QA re-inspection and a hold; release stays a human decision. All costs are estimates in
`config/priors/c5.yaml`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid5

from cportal_core.enums import AlertStatus, RecommendationAction, RecommendationStatus, Severity
from cportal_core.models import (
    Alert,
    Batch,
    CustomerOrder,
    Facility,
    Organization,
    Product,
    Recommendation,
)
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cportal_c5 import MODEL_VERSION
from cportal_c5.config import load_config
from cportal_c5.gallery import NS
from cportal_c5.store import plant_label

KIND = "quality.lot_failed"
WINDOW_DAYS = 14
READY_BEFORE_DUE_D = 2


def _lineage(batch: Batch, key: str) -> dict[str, Any]:
    return {
        "source_id": "c5",
        "source_record_id": key,
        "data_mode": batch.data_mode,
        "is_synthetic": batch.is_synthetic,
        "scenario_id": batch.scenario_id,
        "generator_version": MODEL_VERSION,
    }


def _opt(
    action: RecommendationAction, cost: float, benefit: float, done: date, conf: float, why: str
) -> dict[str, Any]:
    return {
        "action": action,
        "cost": round(cost, 2),
        "benefit": round(benefit, 2),
        "done": done,
        "confidence": conf,
        "why": why,
    }


def options(
    industry: str,
    lot_value: float,
    units: int,
    inspected: date,
    ready_by: date | None,
    revenue: float,
) -> list[dict[str, Any]]:
    """Costed options for one failed lot (pure: unit-tested)."""
    c = load_config()["impact"]
    penalty = float(c["late_penalty_share"]) * revenue
    rework_done = inspected + timedelta(days=int(c["rework_days"][industry]))
    replace_done = inspected + timedelta(days=int(c["replace_days"][industry]))

    def late(done: date) -> bool:
        return ready_by is not None and done > ready_by

    def when(done: date) -> str:
        return f"ready {done:%d %b}" + (" — after the ship-by date" if late(done) else "")

    if industry == "pharma":
        return [
            _opt(
                RecommendationAction.REINSPECT, 0.02 * lot_value, lot_value, rework_done, 0.6,
                "QA review of the flagged units and a tightened re-inspection; a person releases",
            ),
            _opt(
                RecommendationAction.HOLD_SHIPMENT, penalty if late(rework_done) else 0.0,
                lot_value, rework_done, 0.9, "keep the lot in quarantine until QA decides",
            ),
        ]  # fmt: skip
    rework_cost = float(c["rework_cost_share"]) * lot_value
    replace_cost = float(c["replace_cost_share"]) * lot_value
    out = [
        _opt(
            RecommendationAction.REWORK, rework_cost,
            lot_value - (penalty if late(rework_done) else 0.0), rework_done, 0.7,
            f"100 % inspection and repair, {when(rework_done)}",
        ),
        _opt(
            RecommendationAction.REPLACE_PRODUCTION, replace_cost,
            lot_value - (penalty if late(replace_done) else 0.0), replace_done, 0.8,
            f"make the lot again, {when(replace_done)}",
        ),
    ]  # fmt: skip
    if late(replace_done) or late(rework_done):
        kg = units * float(c["kg_per_unit"][industry])
        air = kg * (float(c["air_usd_per_kg"]) - float(c["sea_usd_per_kg"]))
        out.append(
            _opt(
                RecommendationAction.EXPEDITE_AIR, air, penalty, replace_done, 0.6,
                f"if the lot must be remade, fly the {units:,} units: about "
                f"{c['sea_days_saved_by_air']} days faster than sea, avoiding the late claim",
            )
        )  # fmt: skip
        out.append(
            _opt(
                RecommendationAction.NOTIFY_CUSTOMER, 0.0, 0.5 * penalty, inspected, 0.5,
                "tell the buyer now that the lot is in rework; early notice usually halves a "
                "claim (estimate)",
            )
        )  # fmt: skip
    return out


def refresh(session: Session, scenario_id: UUID | None) -> dict[str, int]:
    """Replace the scenario's C5 alerts and recommendations for recent failed lots."""
    old = select(Alert.id).where(Alert.kind == KIND, Alert.scenario_id == scenario_id)
    session.execute(delete(Recommendation).where(Recommendation.alert_id.in_(old)))
    session.execute(delete(Alert).where(Alert.kind == KIND, Alert.scenario_id == scenario_id))
    q = (
        select(Batch, Product, Facility, CustomerOrder, Organization)
        .join(Product, Product.id == Batch.product_id)
        .join(Facility, Facility.id == Batch.facility_id)
        .join(Organization, Organization.id == Facility.organization_id)
        .outerjoin(CustomerOrder, CustomerOrder.id == Batch.order_id)
        .where(Batch.lot_code.like("FG-%"), Batch.status.in_(["rejected", "quarantine"]))
    )
    q = q.where(Batch.scenario_id == scenario_id) if scenario_id else q
    rows = session.execute(q).all()
    if not rows:
        return {"alerts": 0, "recommendations": 0}
    clock = max(b.produced_at for b, *_ in rows)
    alerts = recs = 0
    for batch, product, facility, order, org in rows:
        r = batch.aql_result or {}
        industry = "pharma" if product.sku.startswith("P-") else "garments"
        if batch.produced_at < clock - timedelta(days=WINDOW_DAYS):
            continue
        if industry == "pharma" and r.get("aql_verdict") != "reject":
            continue  # routine QA review: findings within the AQL limit
        inspected = datetime.fromisoformat(r["inspected_at"]).date()
        units = int(min(batch.size_units, order.qty if order else batch.size_units))
        lot_value = units * float(product.unit_value_usd or 0)
        ready_by = order.due_date - timedelta(days=READY_BEFORE_DUE_D) if order else None
        revenue = float(order.revenue_usd or 0) if order else lot_value
        opts = options(industry, lot_value, units, inspected, ready_by, revenue)
        # At risk: the order now depends on rework succeeding (remaking it would be late).
        at_risk = bool(ready_by) and any(o["done"] > ready_by for o in opts[:2])
        key = f"c5:lot:{batch.id}"
        alert_id = uuid5(NS, key)
        verb = "failed AQL" if industry == "garments" else "held for QA review"
        plant = plant_label(org, facility)
        body = (
            f"{r.get('confirmed_defects')} confirmed defects in {r.get('sample_size')} sampled "
            f"(accept ≤ {r.get('accept')})."
        )
        if at_risk and order:
            body += f" Order due {order.due_date:%d %b} is at risk."
        refs = [
            {"type": "batch", "id": str(batch.id)},
            {"type": "facility", "id": str(facility.id)},
        ]
        if order:
            refs.append({"type": "customer_order", "id": str(order.id)})
        session.add(
            Alert(
                id=alert_id,
                **_lineage(batch, key),
                kind=KIND,
                severity=(Severity.HIGH if at_risk else Severity.MEDIUM).value,
                title=f"Lot {batch.lot_code} {verb} at {plant}, line {batch.line}",
                body=body,
                entity_refs=refs,
                status=AlertStatus.OPEN.value,
                dedupe_key=key,
            )
        )
        session.flush()
        alerts += 1
        for i, o in enumerate(opts):
            session.add(
                Recommendation(
                    id=uuid5(NS, f"{key}:{i}"), **_lineage(batch, f"{key}:{o['action']}"),
                    alert_id=alert_id, action_type=str(o["action"]),
                    target_refs=[{"type": "batch", "id": str(batch.id)}]
                    + ([{"type": "customer_order", "id": str(order.id)}] if order else []),
                    params={"units": units, "ready": o["done"].isoformat(),
                            "ready_by": ready_by.isoformat() if ready_by else None,
                            "at_risk": at_risk, "lot_value_usd": round(lot_value, 2)},
                    expected_benefit_usd=o["benefit"], expected_cost_usd=o["cost"],
                    confidence=o["confidence"], rationale=o["why"],
                    evidence_refs=[{"type": "batch", "id": str(batch.id)}],
                    status=RecommendationStatus.PROPOSED.value,
                )
            )  # fmt: skip
            recs += 1
    return {"alerts": alerts, "recommendations": recs}
