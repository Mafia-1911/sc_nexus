"""The C1 supply graph (C1 §4): facilities and ports as nodes, qualified supply relationships as
edges, plus the open orders, bill of materials, inventories, lot quality and linked disruption
events the analytics need.

`from_records` (tests, evaluation over seeds) and `store.load` (API, worker) build the same
`SupplyGraph`: canonical records and ORM rows share attribute names, so one assembly serves
both. Everything derived (demand, input requirements, dependency sets) is computed
here once, so analytics, the LP and the cascade agree on one picture of the network.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import cached_property
from typing import Any
from uuid import UUID

from cportal_core.schemas.records import (
    BatchRecord,
    BomEdgeRecord,
    CustomerOrderRecord,
    DisruptionEventRecord,
    EventEntityLinkRecord,
    FacilityRecord,
    InventoryPositionRecord,
    LocationRecord,
    OrganizationRecord,
    ProductRecord,
    Record,
    SupplyEdgeRecord,
)

from cportal_c1.priors import Priors, load_priors

OPEN_ORDER = ("open", "in_production")
OPEN_EVENT = ("reported", "confirmed", "ongoing")


def port_node(locode: str) -> str:
    return f"port:{locode}"


@dataclass(frozen=True)
class Node:
    id: str  # facility UUID, or "port:<LOCODE>"
    kind: str  # "facility" | "port"
    type: str  # facility type, or "gateway" / "hub"
    name: str
    industry: str | None
    country: str
    cluster: str | None
    lat: float | None
    lon: float | None
    org_key: str | None = None
    headroom: float = 1.0


@dataclass(frozen=True)
class Supply:
    """A qualified supply relationship: `src` may ship `product` to `dst`."""

    id: str
    src: str
    dst: str
    product: str
    share: float
    cap_d: float  # capacity committed to this relationship, units per day
    lead_time_d: float  # order-to-delivery lead time
    transit_d: float  # physical transit into the plant (inventory pipeline)
    mode: str
    route: tuple[str, ...]  # port nodes crossed, in order (hub, gateway)


@dataclass(frozen=True)
class Order:
    id: str
    reference: str
    facility: str
    product: str
    qty: float
    due: date
    revenue_usd: float
    buyer: str
    customer: str | None  # the buyer's DC node
    export_lead_d: float


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    industry: str | None
    unit_value_usd: float


@dataclass(frozen=True)
class EventLink:
    event_id: str
    title: str
    type: str
    status: str
    severity: float
    confidence: float
    duration_d: float | None
    extra_lead_time_d: float | None


@dataclass
class SupplyGraph:
    as_of: datetime
    priors: Priors
    nodes: dict[str, Node]
    supplies: list[Supply]
    products: dict[str, Product]
    bom: dict[str, dict[str, float]]
    orders: list[Order]  # open orders due within the horizon
    inventory: dict[tuple[str, str], float] = field(default_factory=dict)
    quality: dict[str, tuple[int, int]] = field(default_factory=dict)  # node → (lots, rejected)
    events: dict[str, list[EventLink]] = field(default_factory=dict)

    # --- indexes ------------------------------------------------------------------------

    @cached_property
    def gateway(self) -> str:
        return port_node(self.priors.gateway)

    @cached_property
    def inbound(self) -> dict[tuple[str, str], list[Supply]]:
        out: dict[tuple[str, str], list[Supply]] = defaultdict(list)
        for s in self.supplies:
            out[(s.dst, s.product)].append(s)
        return dict(out)

    @cached_property
    def outbound(self) -> dict[tuple[str, str], list[Supply]]:
        out: dict[tuple[str, str], list[Supply]] = defaultdict(list)
        for s in self.supplies:
            out[(s.src, s.product)].append(s)
        return dict(out)

    @cached_property
    def capacity(self) -> dict[tuple[str, str], float]:
        """Units per day a supplier can make of a product (its relationships' capacity)."""
        return {k: sum(s.cap_d for s in v) for k, v in self.outbound.items()}

    @cached_property
    def demand(self) -> dict[tuple[str, str], float]:
        """Daily output each plant needs for its open orders over the horizon."""
        out: dict[tuple[str, str], float] = defaultdict(float)
        for o in self.orders:
            out[(o.facility, o.product)] += o.qty / self.priors.horizon_d
        return dict(out)

    @cached_property
    def bom_order(self) -> list[str]:
        """Products, parents before components (Kahn's algorithm on the BOM)."""
        indegree: dict[str, int] = {p: 0 for p in self.products}
        for comps in self.bom.values():
            for c in comps:
                indegree[c] = indegree.get(c, 0) + 1
        order = [p for p, n in indegree.items() if n == 0]
        for p in order:
            for c in self.bom.get(p, {}):
                indegree[c] -= 1
                if indegree[c] == 0:
                    order.append(c)
        return order

    @cached_property
    def requirements(self) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], float]]:
        """(production, need): daily output per (facility, product) and daily input need per
        (facility, component), exploded from open-order demand through BOM and shares."""
        produce: dict[tuple[str, str], float] = dict(self.demand)
        need: dict[tuple[str, str], float] = defaultdict(float)
        for sku in self.bom_order:
            for (facility, made), rate in list(produce.items()):
                if made != sku or rate <= 0:
                    continue
                for component, qty in self.bom.get(sku, {}).items():
                    req = rate * qty
                    need[(facility, component)] += req
                    for s in self.inbound.get((facility, component), []):
                        key = (s.src, component)
                        produce[key] = produce.get(key, 0.0) + req * s.share
        return produce, dict(need)

    @property
    def production(self) -> dict[tuple[str, str], float]:
        return self.requirements[0]

    @property
    def need(self) -> dict[tuple[str, str], float]:
        return self.requirements[1]

    def flow(self, s: Supply) -> float:
        """Normal daily volume on a relationship."""
        return self.need.get((s.dst, s.product), 0.0) * s.share

    @cached_property
    def makes(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = defaultdict(set)
        for f, p in self.outbound:
            out[f].add(p)
        for f, p in self.demand:
            out[f].add(p)
        return dict(out)

    # --- dependencies -------------------------------------------------------------------

    @cached_property
    def _deps(self) -> dict[tuple[str, str], frozenset[str]]:
        memo: dict[tuple[str, str], frozenset[str]] = {}

        def deps(f: str, p: str, visiting: frozenset[tuple[str, str]]) -> frozenset[str]:
            key = (f, p)
            if key in memo:
                return memo[key]
            out: set[str] = {f}
            for c in self.bom.get(p, {}):
                for s in self.inbound.get((f, c), []):
                    out.add(s.src)
                    out.update(s.route)
                    if (s.src, c) not in visiting:
                        out |= deps(s.src, c, visiting | {key})
            memo[key] = frozenset(out)
            return memo[key]

        for f, products in self.makes.items():
            for p in products:
                deps(f, p, frozenset())
        return memo

    def deps(self, facility: str, product: str) -> frozenset[str]:
        """Every node the output of `product` at `facility` depends on (itself included)."""
        return self._deps.get((facility, product), frozenset({facility}))

    def input_deps(self, facility: str, component: str) -> frozenset[str]:
        """Every node that a plant's supply of `component` depends on."""
        out: set[str] = set()
        for s in self.inbound.get((facility, component), []):
            out.add(s.src)
            out.update(s.route)
            out |= self.deps(s.src, component)
        return frozenset(out)

    @cached_property
    def order_deps(self) -> dict[str, frozenset[str]]:
        return {o.id: self.deps(o.facility, o.product) | {self.gateway} for o in self.orders}

    def industry_of(self, node_id: str) -> str | None:
        return self.nodes[node_id].industry if node_id in self.nodes else None

    def order_industry(self, order: Order) -> str | None:
        product = self.products.get(order.product)
        return product.industry if product else None


# --- building ---------------------------------------------------------------------------


@dataclass
class GraphBuilder:
    """Facility, organization and product rows: canonical records or ORM rows alike."""

    priors: Priors
    as_of: datetime
    facilities: dict[UUID, Any] = field(default_factory=dict)
    orgs: dict[UUID, Any] = field(default_factory=dict)
    points: dict[UUID, tuple[float, float, str | None]] = field(default_factory=dict)
    products: dict[UUID, Any] = field(default_factory=dict)

    def nodes(self) -> dict[str, Node]:
        out: dict[str, Node] = {}
        for f in self.facilities.values():
            org = self.orgs.get(f.organization_id)
            lon, lat, country = self.points.get(f.location_id, (None, None, None))
            out[str(f.id)] = Node(
                id=str(f.id),
                kind="facility",
                type=str(f.facility_type),
                name=f.name,
                industry=str(org.industry) if org and org.industry else None,
                country=(org.country_iso2 if org else None) or country or "BD",
                cluster=f.cluster,
                lat=lat,
                lon=lon,
                org_key=org.name_key if org else None,
                headroom=float((f.capacity or {}).get("headroom", 1.0)),
            )
        for locode, spec in self.priors.ports.items():
            out[port_node(locode)] = Node(
                id=port_node(locode),
                kind="port",
                type=str(spec.get("role", "hub")),
                name=str(spec["name"]),
                industry=None,
                country=locode[:2],
                cluster=None,
                lat=float(spec["lat"]),
                lon=float(spec["lon"]),
            )
        return out

    def supply(self, e: Any, nodes: dict[str, Node]) -> Supply:
        src = nodes[str(e.from_facility_id)]
        sea = str(e.mode) == "sea"
        route: tuple[str, ...] = ()
        transit = self.priors.transit_road
        if sea:
            hub = self.priors.hub_for(src.cluster, src.country)
            route = (*((port_node(hub),) if hub else ()), port_node(self.priors.gateway))
            transit = self.priors.sea_transit(src.country) + self.priors.gateway_dwell
        return Supply(
            id=str(e.id),
            src=str(e.from_facility_id),
            dst=str(e.to_facility_id),
            product=self.products[e.product_id].sku,
            share=float(e.share or 0.0),
            cap_d=float(e.capacity_per_week or 0.0) / 7,
            lead_time_d=float(e.lead_time_mean_d or 0.0),
            transit_d=transit,
            mode=str(e.mode),
            route=route,
        )


def from_records(
    records: Iterable[Record], as_of: datetime, priors: Priors | None = None
) -> SupplyGraph:
    """A graph from canonical records (a synthetic world, or a test fixture)."""
    priors = priors or load_priors()
    b = GraphBuilder(priors, as_of)
    edges: list[SupplyEdgeRecord] = []
    boms: list[BomEdgeRecord] = []
    orders: list[CustomerOrderRecord] = []
    stock: list[InventoryPositionRecord] = []
    batches: list[BatchRecord] = []
    events: dict[UUID, DisruptionEventRecord] = {}
    links: list[EventEntityLinkRecord] = []
    for r in records:
        match r:
            case FacilityRecord():
                b.facilities[r.id] = r
            case OrganizationRecord():
                b.orgs[r.id] = r
            case LocationRecord() if r.geom and r.geom.get("type") == "Point":
                lon, lat = r.geom["coordinates"][:2]
                b.points[r.id] = (float(lon), float(lat), r.country_iso2)
            case ProductRecord():
                b.products[r.id] = r
            case SupplyEdgeRecord():
                edges.append(r)
            case BomEdgeRecord():
                boms.append(r)
            case CustomerOrderRecord():
                orders.append(r)
            case InventoryPositionRecord():
                stock.append(r)
            case BatchRecord():
                batches.append(r)
            case DisruptionEventRecord():
                events[r.id] = r
            case EventEntityLinkRecord():
                links.append(r)
    return assemble(
        b,
        edges=edges,
        bom=[
            (
                b.products[e.parent_product_id].sku,
                b.products[e.component_product_id].sku,
                e.qty_per_unit,
            )
            for e in boms
        ],
        orders=[
            (
                str(o.id),
                o.reference,
                o.facility_id,
                o.product_id,
                o.qty,
                o.due_date,
                o.revenue_usd,
                o.buyer_org_id,
                str(o.status),
            )
            for o in orders
        ],
        stock=[(s.facility_id, s.product_id, s.ts, s.on_hand) for s in stock],
        lots=[(b_.supplier_facility_id, str(b_.status), b_.produced_at) for b_ in batches],
        links=[
            (
                str(link.entity_type),
                link.entity_id,
                events[link.event_id],
                link.impact_hint,
            )
            for link in links
            if link.event_id in events
        ],
        port_events=[e for e in events.values() if e.locodes],
    )


OrderRow = tuple[str, str, UUID | None, UUID, float, date, float | None, UUID, str]


def assemble(
    b: GraphBuilder,
    *,
    edges: Sequence[Any],
    bom: Sequence[tuple[str, str, float]],
    orders: Sequence[OrderRow],
    stock: Sequence[tuple[UUID, UUID, datetime, float]],
    lots: Sequence[tuple[UUID | None, str, datetime | None]],
    links: Sequence[tuple[str, UUID, Any, dict[str, Any]]],
    port_events: Sequence[Any],
) -> SupplyGraph:
    priors = b.priors
    nodes = b.nodes()
    supplies = [
        b.supply(e, nodes)
        for e in edges
        if str(e.from_facility_id) in nodes and str(e.to_facility_id) in nodes
    ]
    products = {
        p.sku: Product(
            p.sku, p.name, str(p.industry) if p.industry else None, p.unit_value_usd or 0.0
        )
        for p in b.products.values()
    }
    bom_map: dict[str, dict[str, float]] = defaultdict(dict)
    for parent, component, qty in bom:
        bom_map[parent][component] = float(qty)
    customer_of: dict[UUID, str] = {}
    for f in b.facilities.values():
        if str(f.facility_type) == "customer_site":
            customer_of.setdefault(f.organization_id, str(f.id))
    start = b.as_of.date()
    end = start + timedelta(days=priors.horizon_d)
    open_orders: list[Order] = []
    for oid, ref, facility, product, qty, due, revenue, buyer, status in orders:
        if facility is None or status not in OPEN_ORDER or not start <= due <= end:
            continue
        if str(facility) not in nodes or product not in b.products:
            continue
        buyer_org = b.orgs.get(buyer)
        customer = customer_of.get(buyer)
        country = nodes[customer].country if customer in nodes else None
        open_orders.append(
            Order(
                id=oid,
                reference=ref,
                facility=str(facility),
                product=b.products[product].sku,
                qty=float(qty),
                due=due,
                revenue_usd=float(revenue or 0.0),
                buyer=buyer_org.name if buyer_org else "",
                customer=customer,
                export_lead_d=priors.export_lead(country),
            )
        )
    inventory: dict[tuple[str, str], float] = {}
    latest: dict[tuple[str, str], datetime] = {}
    for facility, product, ts, on_hand in stock:
        if product not in b.products or ts > b.as_of:
            continue
        key = (str(facility), b.products[product].sku)
        if key not in latest or ts > latest[key]:
            latest[key], inventory[key] = ts, float(on_hand)
    since = b.as_of - timedelta(days=30)
    quality: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for supplier, status, produced in lots:
        if supplier is None or produced is None or not since <= produced <= b.as_of:
            continue
        q = quality[str(supplier)]
        q[0] += 1
        q[1] += status == "quarantine" or status == "rejected"
    linked: dict[str, list[EventLink]] = defaultdict(list)
    for entity_type, entity_id, event, hint in links:
        if entity_type != "facility" or str(entity_id) not in nodes:
            continue
        linked[str(entity_id)].append(event_link(event, hint))
    gateway = priors.gateway
    for event in port_events:
        if gateway in (event.locodes or []) and str(event.status) in OPEN_EVENT:
            linked[port_node(gateway)].append(event_link(event, {}))
    return SupplyGraph(
        as_of=b.as_of,
        priors=priors,
        nodes=nodes,
        supplies=supplies,
        products=products,
        bom=dict(bom_map),
        orders=open_orders,
        inventory=inventory,
        quality={k: (v[0], v[1]) for k, v in quality.items()},
        events={k: v for k, v in linked.items() if v},
    )


def event_link(event: Any, hint: dict[str, Any]) -> EventLink:
    return EventLink(
        event_id=str(event.id),
        title=event.title,
        type=str(event.type),
        status=str(event.status),
        severity=float(event.severity or 0.0),
        confidence=float(event.confidence or 0.0),
        duration_d=event.duration_p50_h / 24 if event.duration_p50_h else None,
        extra_lead_time_d=(
            float(hint["lead_time_extra_d"]) if "lead_time_extra_d" in (hint or {}) else None
        ),
    )


def default_as_of(scenario_start: date | None = None) -> datetime:
    """The world's "now": a scenario's start, else the current time."""
    if scenario_start is None:
        return datetime.now(UTC)
    return datetime.combine(scenario_start, datetime.min.time(), UTC)


__all__ = [
    "EventLink",
    "Node",
    "Order",
    "Product",
    "Supply",
    "SupplyGraph",
    "default_as_of",
    "from_records",
    "port_node",
]
