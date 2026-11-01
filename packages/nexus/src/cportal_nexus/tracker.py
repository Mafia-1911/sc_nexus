"""Shipment tracker (08 §1, NX-R01, NX-AC02): door ETA for every open shipment of a scenario.

Inputs from the database only: legs and their LOCODEs, the linked orders' due dates, C4's
Chattogram port-call predictions (vessel dwell quantiles) and open disruption events with a
duration at a LOCODE (held with probability = their confidence). Writes one `prediction` row per
shipment (capability `nexus`, target `shipment_door_eta`) and `shipment.predicted_eta_p50/p90`.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from functools import cache
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import yaml
from cportal_core.models import (
    CustomerOrder,
    DisruptionEvent,
    Location,
    ModelVersion,
    Prediction,
    Scenario,
    Shipment,
    ShipmentLeg,
    ShipmentOrder,
)
from cportal_core.paths import repo_root
from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.orm import Session, aliased

from cportal_nexus import DOOR_ETA_VERSION, fusion
from cportal_nexus.door_eta import Hold, Leg, Priors, as_hours, due_time, simulate

NS = uuid5(NAMESPACE_URL, "cportal/nexus/door-eta")
TARGET = "shipment_door_eta"
OPEN = ("in_transit", "planned")


@cache
def config() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load((repo_root() / "config/priors/nexus.yaml").read_text())
    return dict(raw["door_eta"])


def priors() -> Priors:
    c = config()
    cd = c["container_dwell_h"]
    return Priors(
        leg_sigma={k: float(v) for k, v in c["leg_sigma"].items()},
        container_dwell_h=(float(cd["p50"]), float(cd["p90"])),
        gateway=str(c["gateway"]),
        samples=int(c["samples"]),
    )


def scenario_now(scenario: Scenario) -> datetime:
    start = str((scenario.definition or {}).get("start"))
    return datetime.combine(datetime.fromisoformat(start).date(), time(0), UTC)


def vessel_pool(session: Session, gateway: str, days: int) -> tuple[list[dict[str, float]], Any]:
    """Quantiles (hours) of C4's most recent port-call predictions at the gateway."""
    last = session.scalar(
        select(func.max(Prediction.as_of)).where(
            Prediction.capability == "c4",
            Prediction.target_type == "port_call",
            Prediction.source_record_id.like(f"{gateway}:%"),
        )
    )
    if last is None:
        return [], None
    rows = session.scalars(
        select(Prediction.quantiles).where(
            Prediction.capability == "c4",
            Prediction.target_type == "port_call",
            Prediction.source_record_id.like(f"{gateway}:%"),
            Prediction.as_of >= last - timedelta(days=days),
        )
    ).all()
    pool = [{k: float(q[k]) for k in ("p10", "p50", "p90") if k in q} for q in rows if q.get("p50")]
    return pool, last


@cache
def type_priors() -> dict[str, dict[str, Any]]:
    raw: dict[str, Any] = yaml.safe_load(
        (repo_root() / "config/priors/disruptions.yaml").read_text()
    )
    return dict(raw["types"])


def stoppage_types() -> frozenset[str]:
    """Event types that stop cargo at a place (capacity ≤ 20 % in disruptions.yaml)."""
    cap = int(config().get("hold_max_capacity_pct", 20))
    return frozenset(k for k, v in type_priors().items() if int(v["capacity_pct"]) <= cap)


def holds(session: Session, scenario_id: UUID) -> list[tuple[Hold, UUID]]:
    fused = fusion.fused_confidence(session, scenario_id)  # NX: fused beats news-only
    rows = session.scalars(
        select(DisruptionEvent).where(
            DisruptionEvent.type.in_(stoppage_types()),
            or_(DisruptionEvent.scenario_id == scenario_id, DisruptionEvent.scenario_id.is_(None)),
            DisruptionEvent.status.notin_(("resolved", "retracted")),
            DisruptionEvent.start_est.is_not(None),
        )
    ).all()
    out = []
    for e in rows:
        if e.start_est is None:
            continue
        prior = type_priors()[e.type]  # no duration on the event: the type's prior (estimate)
        p50 = float(e.duration_p50_h or prior["p50_h"])
        p90 = float(e.duration_p90_h or prior["p90_h"])
        for code in e.locodes or []:
            conf = fused.get(e.id, float(e.confidence or 1.0))
            out.append((Hold(e.title, code, e.start_est, p50, p90, conf), e.id))
    return out


def _legs(session: Session, scenario_id: UUID) -> dict[UUID, list[Leg]]:
    src, dst = aliased(Location), aliased(Location)
    rows = session.execute(
        select(ShipmentLeg, src.locode, dst.locode)
        .join(Shipment, Shipment.id == ShipmentLeg.shipment_id)
        .join(src, src.id == ShipmentLeg.from_location_id)
        .join(dst, dst.id == ShipmentLeg.to_location_id)
        .where(Shipment.scenario_id == scenario_id, Shipment.status.in_(OPEN))
    ).all()
    out: dict[UUID, list[Leg]] = {}
    for leg, a, b in rows:
        if leg.planned_dep is None or leg.planned_arr is None:
            continue
        out.setdefault(leg.shipment_id, []).append(
            Leg(leg.seq, leg.mode, a, b, leg.planned_dep, leg.planned_arr,
                leg.actual_dep, leg.actual_arr)
        )  # fmt: skip
    return out


def _due(session: Session, scenario_id: UUID) -> dict[UUID, Any]:
    rows = session.execute(
        select(ShipmentOrder.shipment_id, func.min(CustomerOrder.due_date))
        .join(CustomerOrder, CustomerOrder.id == ShipmentOrder.order_id)
        .where(ShipmentOrder.scenario_id == scenario_id)
        .group_by(ShipmentOrder.shipment_id)
    ).all()
    return {k: v for k, v in rows}


def refresh(session: Session, scenario_id: UUID) -> dict[str, Any]:
    scenario = session.get(Scenario, scenario_id)
    if scenario is None:
        return {"shipments": 0}
    cfg, pri = config(), priors()
    now = scenario_now(scenario)
    pool, c4_as_of = vessel_pool(session, pri.gateway, int(cfg["vessel_window_days"]))
    hs = holds(session, scenario_id)
    legs, dues = _legs(session, scenario_id), _due(session, scenario_id)
    lineage = {
        "source_id": "nexus",
        "data_mode": "synthetic",
        "is_synthetic": True,
        "scenario_id": scenario_id,
        "generator_version": DOOR_ETA_VERSION,
    }
    mid = uuid5(NS, f"model:{scenario_id}")
    session.merge(
        ModelVersion(
            id=mid, **lineage, source_record_id="door-eta", capability="nexus",
            name="nexus-door-eta-montecarlo", version=DOOR_ETA_VERSION, artifact_uri=None,
            card={"path": "docs/model-cards/nexus-door-eta.md", "method": "Monte Carlo legs"},
            metrics={"vessel_pool": len(pool), "c4_as_of": str(c4_as_of), "holds": len(hs)},
            licence="code only", is_active=True,
        )
    )  # fmt: skip
    session.flush()
    session.execute(
        delete(Prediction).where(
            Prediction.capability == "nexus",
            Prediction.target_type == TARGET,
            Prediction.scenario_id == scenario_id,
        )
    )
    rows, late = [], 0
    for sid, ls in legs.items():
        due = due_time(dues.get(sid))
        eta = simulate(ls, now, due, pri, pool, [h for h, _ in hs], seed=int(cfg["seed"]))
        late += int(eta.on_time_prob is not None and eta.on_time_prob < 0.5)
        rows.append({
            "id": uuid5(NS, f"pred:{sid}"), **lineage, "source_record_id": f"{TARGET}:{sid}",
            "available_at": now, "capability": "nexus", "target_type": TARGET,
            "target_id": sid, "as_of": now, "horizon_h": as_hours(eta.p50, now),
            "value": None if eta.on_time_prob is None else round(eta.on_time_prob, 3),
            "quantiles": {k: as_hours(getattr(eta, k), now) for k in ("p10", "p50", "p90")},
            "dist_params": {"planned": eta.planned.isoformat(),
                            "due": due.isoformat() if due else None, "samples": eta.n},
            "model_version_id": mid,
            "explanation": {
                "drivers": [{"label": k, "hours": v} for k, v in eta.drivers],
                "holds": [{"event_id": str(eid), "title": h.label, "locode": h.locode,
                           "prob": h.prob}
                          for h, eid in hs if any(x.from_locode == h.locode for x in ls)],
                "c4": {"port_call_predictions": len(pool), "as_of": str(c4_as_of)},
            },
            "features_hash": None,
        })  # fmt: skip
        session.execute(
            update(Shipment)
            .where(Shipment.id == sid)
            .values(predicted_eta_p50=eta.p50, predicted_eta_p90=eta.p90)
        )
    if rows:
        session.execute(insert(Prediction), rows)
    return {"shipments": len(rows), "likely_late": late, "holds": len(hs), "vessel_pool": len(pool)}
