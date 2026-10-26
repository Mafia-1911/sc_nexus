"""/graph (C1 §8): the supply network, the criticality leaderboard, node detail and what-ifs.

Reads come from the stored node metrics (`graph_metric`, kept current by the worker), so they
stay inside the read budget; a deterministic what-if runs here (< 2 s, C1-AC04), a Monte Carlo
one is a job. Risk is an adverse attribute: organization names always use the fictional,
guarded name (Q-05), whatever name pack is active.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import pairwise
from typing import Annotated, Any, Literal
from uuid import UUID

from cportal_c1 import MODEL_VERSION, service, store
from cportal_c1.graph import port_node
from cportal_c1.priors import load_priors
from cportal_c1.schemas import DisruptionIn, NodeMetrics, WhatIfRequest
from cportal_core.models import (
    CustomerOrder,
    Facility,
    GraphMetric,
    Location,
    Organization,
    Product,
    Scenario,
    SupplyEdge,
    WhatIfResult,
)
from cportal_core.names import display_name
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from cportal_api.deps import Scope, ScopeDep, SessionDep, meta
from cportal_api.jobs import enqueue
from cportal_api.schemas import (
    CriticalOut,
    Envelope,
    GraphEdgeOut,
    GraphNodeOut,
    JobAccepted,
    NodeDetailOut,
    SupplyGraphOut,
    WhatIfOut,
)

router = APIRouter(tags=["graph"])
OPEN = ("open", "in_production")
EdgeKind = Literal["supply", "import", "export"]


def _scenario(session: SessionDep, scope: Scope) -> Scenario:
    if scope.scenario_id is None:
        raise HTTPException(
            404, "The supply network is synthetic: pick a scenario (C1 runs on scenario worlds)."
        )
    row = session.get(Scenario, scope.scenario_id)
    assert row is not None
    return row


def _metrics(session: SessionDep, scenario: Scenario) -> list[GraphMetric]:
    return list(session.scalars(select(GraphMetric).where(GraphMetric.scenario_id == scenario.id)))


def _note(rows: list[GraphMetric]) -> str | None:
    return None if rows else "Metrics are being computed by the worker (c1:refresh)."


@router.get("/graph", response_model=Envelope[SupplyGraphOut])
def supply_graph(
    session: SessionDep,
    scope: ScopeDep,
    industry: Annotated[str | None, Query(description="garments | pharma")] = None,
) -> Envelope[SupplyGraphOut]:
    """Facilities and ports with their risk, plus material and export flows (network and
    map views). Sea imports are drawn supplier → hub → Chattogram → plant."""
    scenario = _scenario(session, scope)
    priors = load_priors()
    gateway = port_node(priors.gateway)
    metrics = {m.node_id: m for m in _metrics(session, scenario)}
    rows = session.execute(
        select(Facility, Organization, func.ST_X(Location.geom), func.ST_Y(Location.geom))
        .join(Organization, Organization.id == Facility.organization_id)
        .join(Location, Location.id == Facility.location_id)
        .where(Facility.scenario_id == scenario.id)
    ).all()
    keep = {
        str(f.id): (f, o, lon, lat)
        for f, o, lon, lat in rows
        if not industry or o.industry in (industry, None)
    }
    nodes: list[GraphNodeOut] = []
    for node_id, (f, o, lon, lat) in keep.items():
        nodes.append(
            _node(node_id, "facility", f.facility_type, f.name, o, f.cluster, lat, lon, metrics)
        )
    for locode, spec in priors.ports.items():
        nodes.append(
            _node(
                port_node(locode),
                "port",
                str(spec.get("role", "hub")),
                str(spec["name"]),
                None,
                None,
                float(spec["lat"]),
                float(spec["lon"]),
                metrics,
            )
        )
    sku = {pid: code for pid, code in session.execute(select(Product.id, Product.sku))}
    flows: dict[tuple[str, str, EdgeKind], dict[str, Any]] = {}

    def add(a: str, b: str, kind: EdgeKind, product: str, share: float, mode: str) -> None:
        edge = flows.setdefault(
            (a, b, kind), {"products": set(), "share": 0.0, "mode": mode, "relationships": 0}
        )
        edge["products"].add(product)
        edge["share"] = max(edge["share"], share)
        edge["relationships"] += 1

    for e in session.scalars(select(SupplyEdge).where(SupplyEdge.scenario_id == scenario.id)):
        src, dst = str(e.from_facility_id), str(e.to_facility_id)
        if src not in keep or dst not in keep:
            continue
        product = sku.get(e.product_id, "?")
        if e.mode == "sea":
            supplier = keep[src][0]
            hub = priors.hub_for(supplier.cluster, keep[src][1].country_iso2)
            hops = [src, *((port_node(hub),) if hub else ()), gateway, dst]
            for a, b in pairwise(hops):
                add(a, b, "import", product, e.share or 0.0, "sea")
        else:
            add(src, dst, "supply", product, e.share or 0.0, e.mode or "road")
    customer_of = {
        o.id: str(f.id) for f, o, _, _ in keep.values() if f.facility_type == "customer_site"
    }
    for facility_id, buyer, product_id in session.execute(
        select(CustomerOrder.facility_id, CustomerOrder.buyer_org_id, CustomerOrder.product_id)
        .where(CustomerOrder.scenario_id == scenario.id, CustomerOrder.status.in_(OPEN))
        .distinct()
    ):
        plant = str(facility_id)
        if plant not in keep:
            continue
        add(plant, gateway, "export", sku.get(product_id, "?"), 1.0, "road")
        if buyer in customer_of:
            add(gateway, customer_of[buyer], "export", sku.get(product_id, "?"), 1.0, "sea")
    edges = [
        GraphEdgeOut(
            source=a,
            target=b,
            kind=kind,
            products=sorted(v["products"]),
            share=round(v["share"], 3),
            mode=v["mode"],
            relationships=v["relationships"],
        )
        for (a, b, kind), v in flows.items()
    ]
    stored = list(metrics.values())
    return Envelope(
        data=SupplyGraphOut(nodes=nodes, edges=edges),
        meta=meta(
            stored or [r[0] for r in rows], scope, model_version=MODEL_VERSION, note=_note(stored)
        ),
    )


def _node(
    node_id: str,
    kind: str,
    node_type: str,
    name: str,
    org: Organization | None,
    cluster: str | None,
    lat: float | None,
    lon: float | None,
    metrics: dict[str, GraphMetric],
) -> GraphNodeOut:
    m = metrics.get(node_id)
    return GraphNodeOut(
        id=node_id,
        kind=kind,
        type=node_type,
        name=name,
        organization=display_name(org.name_key, org.name, adverse=True) if org else None,
        industry=org.industry if org else None,
        country=(org.country_iso2 if org else node_id[5:7]) or "BD",
        cluster=cluster,
        lat=lat,
        lon=lon,
        is_fictional=bool(org.is_fictional) if org else False,
        risk_score=m.risk_score if m else None,
        risk_band=m.risk_band if m else None,
        dominated_value_usd=m.dominated_value_usd if m else 0.0,
        dominated_orders=m.dominated_orders if m else 0,
        downstream_open_order_value_usd=m.downstream_open_order_value_usd if m else 0.0,
        tts_d=m.tts_d if m else None,
        tts_capped=m.tts_capped if m else False,
        ttr_d=m.ttr_d if m else None,
    )


@router.get("/graph/critical", response_model=Envelope[CriticalOut])
def critical(
    session: SessionDep,
    scope: ScopeDep,
    metric: Annotated[str, Query(pattern="^(dominance|downstream|tts_gap|risk)$")] = "dominance",
    industry: Annotated[str | None, Query(description="garments | pharma")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Envelope[CriticalOut]:
    """The criticality leaderboard (C1-R01, C1-R03): single points of failure first."""
    scenario = _scenario(session, scope)
    rows = _metrics(session, scenario)
    ranked = service.rank(store.metrics_from_rows(rows), metric, industry)[:limit]
    tts_lt_ttr = [
        m.node_id
        for m in ranked
        if m.tts_d is not None and m.ttr_d is not None and not m.tts_capped and m.tts_d < m.ttr_d
    ]
    return Envelope(
        data=CriticalOut(metric=metric, items=ranked, tts_below_ttr=tts_lt_ttr),
        meta=meta(rows, scope, model_version=MODEL_VERSION, note=_note(rows)),
    )


@router.get("/graph/nodes/{node_id}", response_model=Envelope[NodeDetailOut])
def node_detail(node_id: str, session: SessionDep, scope: ScopeDep) -> Envelope[NodeDetailOut]:
    """One node: risk with drivers, inputs and their concentration, customers, linked events,
    the orders it alone can stop, and pre-filled what-if defaults (C1-AC06)."""
    scenario = _scenario(session, scope)
    row = session.scalar(
        select(GraphMetric).where(
            GraphMetric.scenario_id == scenario.id, GraphMetric.node_id == node_id
        )
    )
    if row is None:
        raise HTTPException(404, f"unknown node {node_id!r} (or metrics not computed yet)")
    metrics = store.metrics_from_rows([row])[0]
    names = {
        str(f.id): f.name
        for f in session.scalars(select(Facility).where(Facility.scenario_id == scenario.id))
    }
    sku = {pid: code for pid, code in session.execute(select(Product.id, Product.sku))}
    inputs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    customers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if row.node_kind == "facility":
        fid = UUID(node_id)
        for e in session.scalars(
            select(SupplyEdge).where(
                SupplyEdge.scenario_id == scenario.id,
                (SupplyEdge.to_facility_id == fid) | (SupplyEdge.from_facility_id == fid),
            )
        ):
            item = {
                "share": e.share,
                "mode": e.mode,
                "lead_time_d": e.lead_time_mean_d,
                "capacity_per_week": e.capacity_per_week,
            }
            if e.to_facility_id == fid:
                other = str(e.from_facility_id)
                inputs[sku.get(e.product_id, "?")].append(
                    {**item, "node_id": other, "name": names.get(other, other)}
                )
            else:
                other = str(e.to_facility_id)
                customers[sku.get(e.product_id, "?")].append(
                    {**item, "node_id": other, "name": names.get(other, other)}
                )
    orders = []
    if metrics.dominated_order_ids:
        buyers = {
            oid: name for oid, name in session.execute(select(Organization.id, Organization.name))
        }
        for o in session.scalars(
            select(CustomerOrder)
            .where(CustomerOrder.id.in_([UUID(i) for i in metrics.dominated_order_ids]))
            .order_by(CustomerOrder.due_date)
        ):
            orders.append(
                {
                    "order_id": str(o.id),
                    "reference": o.reference,
                    "product": sku.get(o.product_id, "?"),
                    "facility": names.get(str(o.facility_id), ""),
                    "buyer": buyers.get(o.buyer_org_id, ""),
                    "due": o.due_date.isoformat(),
                    "revenue_usd": o.revenue_usd,
                }
            )
    events = store.linked_events(session, scenario, node_id)
    defaults = service.defaults_for(load_priors(), node_id, row.node_type, events)
    return Envelope(
        data=NodeDetailOut(
            metrics=metrics,
            inputs=dict(inputs),
            customers=dict(customers),
            events=[e.__dict__ for e in events],
            dominated_orders=orders,
            whatif_defaults=defaults,
        ),
        meta=meta([row], scope, model_version=MODEL_VERSION),
    )


@router.post(
    "/graph/whatif",
    response_model=Envelope[WhatIfOut],
    responses={202: {"model": JobAccepted, "description": "Monte Carlo runs as a job"}},
)
def run_whatif(
    body: WhatIfRequest, session: SessionDep, scope: ScopeDep
) -> Envelope[WhatIfOut] | JSONResponse:
    """A cascade what-if (C1-R02). Deterministic (`mc_runs` = 0) answers now; with Monte
    Carlo runs it is queued (202) and its result appears at `/graph/whatif/{id}`."""
    scenario = _scenario(session, scope)
    if body.mc_runs:
        accepted = enqueue(
            session,
            "c1.whatif",
            {"scenario": scenario.key, "request": body.model_dump(mode="json")},
        )
        return JSONResponse(accepted.model_dump(mode="json"), status_code=status.HTTP_202_ACCEPTED)
    graph = store.load(session, scenario)
    try:
        result = service.what_if(graph, body)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    whatif_id = store.save_whatif(session, scenario, result, graph.as_of)
    session.commit()
    row = session.get(WhatIfResult, whatif_id)
    return Envelope(
        data=WhatIfOut(id=whatif_id, scenario=scenario.key, **result.model_dump()),
        meta=meta([row], scope, model_version=MODEL_VERSION),
    )


@router.get("/graph/whatif/{whatif_id}", response_model=Envelope[WhatIfOut])
def get_whatif(whatif_id: UUID, session: SessionDep, scope: ScopeDep) -> Envelope[WhatIfOut]:
    row = session.get(WhatIfResult, whatif_id)
    if row is None:
        raise HTTPException(404, f"unknown what-if {whatif_id}")
    scenario = session.get(Scenario, row.scenario_id) if row.scenario_id else None
    return Envelope(
        data=WhatIfOut(id=row.id, scenario=scenario.key if scenario else None, **row.result),
        meta=meta([row], scope, model_version=row.model_version),
    )


__all__ = ["DisruptionIn", "NodeMetrics", "router"]
