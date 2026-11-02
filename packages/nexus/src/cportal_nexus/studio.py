"""Scenario Studio (08 §2, NX-R02, NX-AC05): "with Nexus vs without", per scenario.

Two policies on the same seeded inputs, as of the scenario's `now`:
- `baseline`: do nothing;
- `nexus_recommended`: accept every proposed action with positive expected value.

Production (C1): the scenario's open disruption alerts become C1 disruptions at their P90
duration (K-05 counts P90 lateness); with Nexus, the buffer and pull-forward units are added to
the plants' input inventory (pull-forward × its feasible share) and the cascade is rerun.
Quality (C5): an order at risk from a failed lot is saved with Nexus when its best positive-value
option is ready by the order's date. In transit: door-ETA P90 later than due (actions here do
not change transit). K-06 = on-time share of open orders; K-07 = inland CO2e per TEU (DESNZ via
C3) plus the CO2e the actions add (air instead of sea). Deterministic: no sampling here.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import yaml
from cportal_c1 import service as c1
from cportal_c1 import store as c1_store
from cportal_c1.graph import SupplyGraph
from cportal_c1.schemas import DisruptionIn, WhatIfRequest, WhatIfResult
from cportal_c3 import store as c3_store
from cportal_c3.priors import load_priors as c3_priors
from cportal_core.models import (
    Alert,
    DisruptionEvent,
    EmissionFactor,
    Location,
    Prediction,
    Recommendation,
    Scenario,
    ScenarioResult,
    Shipment,
    ShipmentLeg,
)
from cportal_core.paths import repo_root
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, aliased

from cportal_nexus import BUFFER_VERSION, buffer
from cportal_nexus.tracker import scenario_now

NS = uuid5(NAMESPACE_URL, "cportal/nexus/studio")
POLICIES = ("baseline", "nexus_recommended")


def config() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load((repo_root() / "config/priors/nexus.yaml").read_text())
    return dict(raw["studio"])


def _alerts(
    session: Session, scenario: Scenario, now: datetime
) -> list[tuple[Alert, DisruptionEvent]]:
    seen = func.coalesce(DisruptionEvent.available_at, DisruptionEvent.first_seen)
    return list(
        session.execute(
            select(Alert, DisruptionEvent)
            .join(DisruptionEvent, DisruptionEvent.id == Alert.event_id)
            .where(
                Alert.kind == "disruption",
                Alert.status.in_(("open", "ack")),
                or_(Alert.scenario_id == scenario.id, Alert.scenario_id.is_(None)),
                or_(seen.is_(None), seen <= now),
            )
        ).tuples()
    )


def _disruptions(
    session: Session,
    g: SupplyGraph,
    scenario: Scenario,
    now: datetime,
    alerts: list[Any],
    which: str,
) -> list[DisruptionIn]:
    """The scenario's open alerts as C1 disruptions (buffer.window: the same definition the
    recommendation engine uses); one per node, the longest."""
    by_node: dict[str, DisruptionIn] = {}
    for _alert, e in alerts:
        when = buffer.window(e, now, which)
        if when is None:
            continue
        cap = float(buffer.CAPACITY_BY_TYPE.get(e.type, 40))
        for d in buffer.disruptions(buffer._nodes(session, g, e, scenario), when, cap):
            old = by_node.get(d.node_id)
            if old is None or d.start_d + d.duration_d > old.start_d + old.duration_d:
                by_node[d.node_id] = d
    return list(by_node.values())[:10]


def _accepted(session: Session, scenario: Scenario, alert_ids: set[Any]) -> list[Recommendation]:
    rows = session.scalars(
        select(Recommendation).where(
            Recommendation.scenario_id == scenario.id,
            Recommendation.status.in_(("proposed", "accepted")),
        )
    ).all()
    return [
        r for r in rows
        if (r.expected_benefit_usd or 0) > (r.expected_cost_usd or 0)
        and (r.source_id != "nexus" or r.alert_id in alert_ids)
    ]  # fmt: skip


def _with_stock(g: SupplyGraph, recs: list[Recommendation]) -> SupplyGraph:
    inv = dict(g.inventory)
    for r in recs:
        if r.action_type not in ("increase_safety_stock", "pull_forward_po"):
            continue
        for t in r.target_refs:
            key = (str(t["facility_id"]), str(t["product"]))
            share = (
                float(t.get("feasible_share", 1.0)) if r.action_type == "pull_forward_po" else 1.0
            )
            base = inv.get(key, g.need.get(key, 0.0) * g.priors.default_cover_d)
            inv[key] = base + float(t["units"]) * share
    return dataclasses.replace(g, inventory=inv)


def _quality(recs: list[Recommendation]) -> dict[str, Any]:
    """Orders at risk from failed lots (C5), and which Nexus saves (best on-time option)."""
    by_order: dict[str, list[Recommendation]] = {}
    for r in recs:
        if r.source_id != "c5" or not (r.params or {}).get("at_risk"):
            continue
        for ref in r.target_refs or []:
            if ref.get("type") == "customer_order":
                by_order.setdefault(str(ref["id"]), []).append(r)
    saved, cost, actions = 0, 0.0, []
    for _order, options in by_order.items():
        on_time = [o for o in options if o.params.get("ready") and o.params.get("ready_by")
                   and o.params["ready"] <= o.params["ready_by"]]  # fmt: skip
        if on_time:
            best = max(
                on_time, key=lambda o: (o.expected_benefit_usd or 0) - (o.expected_cost_usd or 0)
            )
            saved += 1
            cost += float(best.expected_cost_usd or 0)
            actions.append(best)
    return {"at_risk": len(by_order), "saved": saved, "cost": cost, "actions": actions}


def _in_transit_late(session: Session, scenario: Scenario) -> tuple[int, int]:
    rows = (
        session.execute(
            select(Prediction.value).where(
                Prediction.capability == "nexus",
                Prediction.target_type == "shipment_door_eta",
                Prediction.scenario_id == scenario.id,
            )
        )
        .scalars()
        .all()
    )
    # P90 door time later than due ⇔ P(on time) < 0.9.
    late = sum(1 for v in rows if v is not None and v < 0.9)
    return late, len(rows)


def _inland_co2e(session: Session, scenario: Scenario) -> dict[str, Any]:
    cfg, c3p = config(), c3_priors()
    factors = c3_store.factors(session, c3p)
    src, dst = aliased(Location), aliased(Location)
    km = func.ST_Distance(func.geography(src.geom), func.geography(dst.geom)) / 1000.0
    rows = session.execute(
        select(ShipmentLeg.mode, km, func.jsonb_array_length(Shipment.containers))
        .join(Shipment, Shipment.id == ShipmentLeg.shipment_id)
        .join(src, src.id == ShipmentLeg.from_location_id)
        .join(dst, dst.id == ShipmentLeg.to_location_id)
        .where(
            Shipment.scenario_id == scenario.id,
            Shipment.status.in_(("in_transit", "planned")),
            ShipmentLeg.mode.in_(("road", "rail", "barge")),
            ShipmentLeg.actual_arr.is_(None),
        )
    ).all()
    total, teu = 0.0, 0.0
    by_mode: dict[str, float] = {}
    for mode, dist, n in rows:
        if dist is None:
            continue
        q = max(int(n or 0), 1)
        kg = (
            float(factors[mode]["value"])
            * q
            * float(c3p["cargo_t_per_teu"])
            * float(dist)
            * float(cfg["detour"][mode])
        )
        total += kg
        teu += q
        by_mode[mode] = round(by_mode.get(mode, 0.0) + kg, 1)
    return {
        "kg_per_teu": round(total / teu, 1) if teu else None,
        "teu_moves": teu,
        "by_mode_kg": by_mode,
        "factors": {
            m: {k: factors[m][k] for k in ("id", "label", "value", "year")} for m in by_mode
        },
    }


def _air_delta(session: Session, recs: list[Recommendation]) -> dict[str, Any]:
    cfg = config()
    kg_per_unit = float(
        yaml.safe_load((repo_root() / "config/priors/c5.yaml").read_text())
        .get("impact", {}).get("kg_per_unit", {}).get("garments", 0.25)
    )  # fmt: skip

    def factor(spec: dict[str, Any]) -> EmissionFactor | None:
        q = select(EmissionFactor).where(
            EmissionFactor.vehicle_class == spec["vehicle_class"], EmissionFactor.unit == "tonne.km"
        )
        if spec.get("fuel"):
            q = q.where(EmissionFactor.fuel == spec["fuel"])
        return session.scalars(q.order_by(EmissionFactor.year.desc())).first()

    air, sea = factor(cfg["air"]), factor(cfg["sea"])
    tonnes = sum(float(r.params.get("units", 0)) * kg_per_unit / 1000 for r in recs
                 if r.action_type == "expedite_air")  # fmt: skip
    if not tonnes or air is None or sea is None:
        return {"kg": 0.0, "tonnes_flown": round(tonnes, 3)}
    kg = tonnes * (air.value * float(cfg["air"]["km"]) - sea.value * float(cfg["sea"]["km"]))
    return {
        "kg": round(kg, 1),
        "tonnes_flown": round(tonnes, 3),
        "factors": {"air": {"id": str(air.id), "value": air.value, "year": air.year},
                    "sea": {"id": str(sea.id), "value": sea.value, "year": sea.year}},
    }  # fmt: skip


def _late(res: WhatIfResult | None, rerouted: dict[str, float]) -> tuple[float, float]:
    """Expected late orders and revenue: a rerouted order blocked at the gateway is saved with
    the alternative gateway's feasible share (A-098); input-short orders stay as C1 says."""
    if res is None:
        return 0.0, 0.0
    count = revenue = 0.0
    for o in res.impacted_orders:
        if not o.late:
            continue
        w = 1.0 - rerouted.get(o.order_id, 0.0) if o.cause == "gateway" else 1.0
        count += w
        revenue += w * o.revenue_usd
    return round(count, 2), round(revenue, 2)


def _kpis(
    late: tuple[float, float], n_orders: int, quality_late: int, transit: tuple[int, int]
) -> dict[str, Any]:
    prod_late, prod_value = late
    total = prod_late + quality_late
    return {
        "orders_at_risk": {"production": prod_late, "quality": quality_late,
                           "in_transit": transit[0], "total": round(total + transit[0], 2)},
        "revenue_at_risk_usd": prod_value,
        "otif": round(1 - total / n_orders, 4) if n_orders else None,
    }  # fmt: skip


def compare(session: Session, scenario: Scenario) -> dict[str, Any]:
    cfg = config()
    now = scenario_now(scenario)
    g = c1_store.load(session, scenario)
    alerts = _alerts(session, scenario, now)
    recs = _accepted(session, scenario, {a.id for a, _ in alerts})
    stock = [r for r in recs if r.action_type in ("increase_safety_stock", "pull_forward_po")]
    g_nexus = _with_stock(g, stock)
    runs: dict[str, tuple[WhatIfResult | None, WhatIfResult | None]] = {}
    disruptions: dict[str, list[DisruptionIn]] = {}
    for which in ("p50", "p90"):
        disruptions[which] = _disruptions(session, g, scenario, now, alerts, which)
        req = WhatIfRequest(disruptions=disruptions[which]) if disruptions[which] else None
        runs[which] = (c1.what_if(g, req), c1.what_if(g_nexus, req)) if req else (None, None)
    base, nexus = runs["p90"]  # K-05 counts P90 lateness
    reroutes = [r for r in recs if r.action_type == "reroute"]
    rerouted = {str(t["order_id"]): float(r.params.get("feasible_share", 0.0))
                for r in reroutes for t in r.target_refs}  # fmt: skip
    q = _quality(recs)
    transit = _in_transit_late(session, scenario)
    n = len(g.orders)
    inland = _inland_co2e(session, scenario)
    air = _air_delta(session, q["actions"])
    k_base = _kpis(_late(base, {}), n, q["at_risk"], transit)
    k_nexus = _kpis(_late(nexus, rerouted), n, q["at_risk"] - q["saved"], transit)
    action_cost = sum(float(r.expected_cost_usd or 0) for r in stock + reroutes) + q["cost"]
    production_avoided = (k_base["revenue_at_risk_usd"] - k_nexus["revenue_at_risk_usd"]) * float(
        cfg["penalty_rate"]
    )
    quality_avoided = sum(float(r.expected_benefit_usd or 0) for r in q["actions"])  # C5's estimate
    avoided = production_avoided + quality_avoided
    p50 = {
        name: dict(zip(("production_late", "revenue_at_risk_usd"), _late(r, rr), strict=True))
        for name, r, rr in zip(POLICIES, runs["p50"], ({}, rerouted), strict=True)
    }
    for k, extra in ((k_base, 0.0), (k_nexus, action_cost)):
        k["action_cost_usd"] = round(extra, 2)
        k["co2e_inland_kg_per_teu"] = inland["kg_per_teu"]
        k["co2e_actions_kg"] = 0.0 if k is k_base else air["kg"]
    accepted = stock + reroutes + q["actions"]
    return {
        "as_of": now.isoformat(),
        "policies": {"baseline": k_base, "nexus_recommended": k_nexus},
        "at_p50": p50,
        "delta": {
            "orders_saved": round(
                k_base["orders_at_risk"]["total"] - k_nexus["orders_at_risk"]["total"], 2
            ),
            "otif_pts": None if k_base["otif"] is None or k_nexus["otif"] is None
            else round((k_nexus["otif"] - k_base["otif"]) * 100, 1),
            "lateness_cost_avoided_usd": round(avoided, 2),
            "of_which_quality_usd": round(quality_avoided, 2),
            "action_cost_usd": round(action_cost, 2),
            "net_usd": round(avoided - action_cost, 2),
            "co2e_kg": air["kg"],
        },
        "inputs": {
            "open_orders": n,
            "disruptions": {w: [d.model_dump() for d in ds] for w, ds in disruptions.items()},
            "alerts": [{"alert_id": str(a.id), "event_id": str(e.id), "title": e.title}
                       for a, e in alerts],
            "actions": [{"id": str(r.id), "type": r.action_type, "source": r.source_id,
                         "cost_usd": r.expected_cost_usd, "benefit_usd": r.expected_benefit_usd,
                         "confidence": r.confidence, "rationale": r.rationale} for r in accepted],
            "co2e": {"inland": inland, "air": air},
        },
    }  # fmt: skip


def refresh(session: Session, scenario_id: Any) -> dict[str, Any]:
    scenario = session.get(Scenario, scenario_id)
    if scenario is None:
        return {}
    out = compare(session, scenario)
    session.execute(
        delete(ScenarioResult).where(
            ScenarioResult.run_scenario_id == scenario.id, ScenarioResult.capability == "nexus"
        )
    )
    session.add(
        ScenarioResult(
            id=uuid5(NS, str(scenario.id)), source_id="nexus", source_record_id=scenario.key,
            data_mode="synthetic", is_synthetic=True, scenario_id=scenario.id,
            generator_version=BUFFER_VERSION, available_at=scenario_now(scenario),
            run_scenario_id=scenario.id, capability="nexus",
            kpis={"policies": out["policies"], "delta": out["delta"], "at_p50": out["at_p50"],
                  "as_of": out["as_of"]},
            artifacts=out["inputs"],
        )
    )  # fmt: skip
    return out["delta"]
