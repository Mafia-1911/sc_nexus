"""Synthetic world v0 (03 §4): fictional firms at real clusters, real ports and HS codes.

Deterministic for a (scenario, seed): every id is a UUIDv5 of the scenario and a natural key,
so re-seeding upserts the same rows. Real infrastructure (ports, ICDs, sea lanes) is referenced
by UN/LOCODE and comes from the replayed sources; firms, facilities, orders, inventory,
shipments and batches are fictional and carry `is_synthetic` + `scenario_id`.

Quantities, lead times and transit times marked "estimate" are placeholders until C1/C3/C5
calibrate them; CALIBRATION.md lists what is calibrated today.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from typing import Any
from uuid import UUID

import yaml
from cportal_connectors.canonical import ParseContext, scenario_uuid
from cportal_core.enums import (
    BatchStatus,
    CargoProfile,
    EventClassifier,
    FacilityType,
    Industry,
    LocationKind,
    OrderStatus,
    OrgKind,
    ShipmentStatus,
    TransportEventType,
    TransportMode,
)
from cportal_core.ids import location_id
from cportal_core.names import fictional_name
from cportal_core.paths import config_dir
from cportal_core.schemas.records import (
    BatchRecord,
    BomEdgeRecord,
    CustomerOrderRecord,
    FacilityRecord,
    InventoryPositionRecord,
    LaneRecord,
    LocationRecord,
    OrganizationRecord,
    ProductRecord,
    Record,
    ScenarioRecord,
    ShipmentLegRecord,
    ShipmentOrderRecord,
    ShipmentRecord,
    SupplyEdgeRecord,
    TransportEventRecord,
    point,
)

GENERATOR = "cportal-sim/world/0.1.0"
SOURCE = "sim"
KM_PER_DEG = 111.32
DEFAULT_START = date(2026, 10, 26)

# Transit-time estimates in hours (to be replaced by C3's models and C4's port predictions).
INLAND_H = {
    "road": 14.0,  # Dhaka area → Chattogram by truck, incl. congestion (estimate)
    "rail": 30.0,  # Kamalapur ICD → Chattogram incl. ICD dwell (estimate)
    "barge": 60.0,  # Pangaon → Chattogram (estimate)
    "local": 3.0,  # CEPZ/KEPZ → port (estimate)
}
PORT_DWELL_H = 72.0  # gate-in to vessel departure at Chattogram (estimate)
TRANSSHIP_DWELL_H = 72.0  # at the hub (estimate)
SEA_H = {  # incl. port-to-port service time (estimates)
    ("BDCGP", "SGSIN"): 120.0,
    ("BDCGP", "LKCMB"): 96.0,
    ("BDCGP", "MYPKG"): 108.0,
    ("SGSIN", "NLRTM"): 624.0,
    ("LKCMB", "NLRTM"): 528.0,
    ("SGSIN", "USLAX"): 480.0,
    ("MYPKG", "USLAX"): 528.0,
}
# ISO 2859-1, general inspection level II, AQL 2.5, single sampling, normal inspection.
AQL_25 = [  # (max lot size, sample size, accept, reject)
    (50, 8, 0, 1),
    (90, 13, 1, 2),
    (150, 20, 1, 2),
    (280, 32, 2, 3),
    (500, 50, 3, 4),
    (1200, 80, 5, 6),
    (3200, 125, 7, 8),
]
INDUSTRY_PREFIX = {"garments": "G", "pharma": "P"}
HERO_FACTORY = "garment_exporter_1.garment_factory.1"  # "Factory A" in the golden path
OVERSEAS_COUNTRY = {"IN": "IN", "CN": "CN", "US": "US", "NL": "NL", "LK": "LK"}


@dataclass
class World:
    scenario_key: str
    scenario_id: UUID
    seed: int
    start: datetime
    records: list[Record] = field(default_factory=list)
    orgs: dict[str, OrganizationRecord] = field(default_factory=dict)
    facilities: dict[str, FacilityRecord] = field(default_factory=dict)
    facility_types: dict[str, str] = field(default_factory=dict)
    facility_cluster: dict[str, str] = field(default_factory=dict)
    products: dict[str, ProductRecord] = field(default_factory=dict)
    edges: list[SupplyEdgeRecord] = field(default_factory=list)
    orders: list[CustomerOrderRecord] = field(default_factory=list)
    shipments: list[ShipmentRecord] = field(default_factory=list)
    hero: dict[str, Any] = field(default_factory=dict)

    def add(self, *records: Record) -> None:
        self.records.extend(records)

    def by_table(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.records:
            counts[r.table] = counts.get(r.table, 0) + 1
        return counts


def _yaml(*parts: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(config_dir().joinpath(*parts).read_text("utf-8"))
    return data


def _jitter(lat: float, lon: float, km: float, rng: random.Random) -> tuple[float, float]:
    r = km * math.sqrt(rng.random())
    theta = rng.uniform(0, 2 * math.pi)
    dlat = r * math.cos(theta) / KM_PER_DEG
    dlon = r * math.sin(theta) / (KM_PER_DEG * math.cos(math.radians(lat)))
    return round(lat + dlat, 5), round(lon + dlon, 5)


def _aql(lot_size: int) -> tuple[int, int, int]:
    for max_lot, n, ac, re in AQL_25:
        if lot_size <= max_lot:
            return n, ac, re
    return AQL_25[-1][1:]


def _beta_binomial(n: int, a: float, b: float, rng: random.Random) -> tuple[int, float]:
    p = rng.betavariate(a, b)
    return sum(rng.random() < p for _ in range(n)), p


class WorldBuilder:
    def __init__(self, scenario_key: str, seed: int, start: date) -> None:
        self.rng = random.Random(f"{seed}:world")
        self.ctx = ParseContext.synthetic(SOURCE, scenario_key, GENERATOR)
        start_ts = datetime.combine(start, time(0), UTC)
        self.world = World(scenario_key, scenario_uuid(scenario_key), seed, start_ts)
        self.clusters: dict[str, Any] = _yaml("world", "clusters.yaml")

    # --- helpers ---------------------------------------------------------------------------

    def lin(self, key: object, available_at: datetime | None = None) -> dict[str, Any]:
        return self.ctx.lineage(key, available_at=available_at)

    def rid(self, table: str, key: object) -> UUID:
        return self.ctx.rid(table, key)

    def site(self, key: str, name: str, lat: float, lon: float, cluster: str | None) -> UUID:
        loc_id = self.rid("location", f"site:{key}")
        self.world.add(
            LocationRecord(
                id=loc_id,
                **self.lin(f"site:{key}"),
                name=name,
                kind=LocationKind.SITE,
                cluster=cluster,
                country_iso2=self.clusters["overseas"].get(cluster or "", {}).get("country", "BD"),
                geom=point(lon, lat),
            )
        )
        return loc_id

    def org(self, key: str, kind: OrgKind, industry: Industry | None, country: str) -> UUID:
        org_id = self.rid("organization", key)
        record = OrganizationRecord(
            id=org_id,
            **self.lin(key),
            name=fictional_name(key, key.replace("_", " ").title()),
            name_key=key,
            country_iso2=country,
            kind=kind,
            industry=industry,
            is_fictional=True,
        )
        self.world.orgs[key] = record
        self.world.add(record)
        return org_id

    def facility(
        self,
        key: str,
        org_key: str,
        ftype: FacilityType,
        cluster: str,
        capacity: dict[str, Any],
        overseas: bool = False,
    ) -> FacilityRecord:
        spot = self.clusters["overseas" if overseas else "clusters"][cluster]
        lat, lon = _jitter(spot["lat"], spot["lon"], spot.get("jitter_km", 8), self.rng)
        org = self.world.orgs[org_key]
        title = cluster.replace("_", " ").title()
        name = f"{org.name} – {title} unit"
        loc_id = self.site(key, f"Site of {name}", lat, lon, cluster)
        record = FacilityRecord(
            id=self.rid("facility", key),
            **self.lin(key),
            organization_id=org.id,
            name=name,
            name_key=key,
            facility_type=ftype,
            location_id=loc_id,
            cluster=cluster,
            capacity=capacity,
            certifications=["fictional"],
        )
        self.world.facilities[key] = record
        self.world.facility_types[key] = ftype
        self.world.facility_cluster[key] = cluster
        self.world.add(record)
        return record

    # --- build steps -----------------------------------------------------------------------

    def scenario(self, definition: dict[str, Any]) -> None:
        w = self.world
        w.add(
            ScenarioRecord(
                id=w.scenario_id,
                **self.lin(w.scenario_key, available_at=w.start),
                key=w.scenario_key,
                name=definition.get("name", w.scenario_key),
                definition=definition,
                seed=w.seed,
                is_baseline=w.scenario_key == "baseline",
                created_by=GENERATOR,
            )
        )

    def products(self, pack: dict[str, Any]) -> None:
        prefix = INDUSTRY_PREFIX[pack["industry"]]
        for code, spec in pack["products"].items():
            sku = f"{prefix}-{code}"
            record = ProductRecord(
                id=self.rid("product", sku),
                **self.lin(sku),
                sku=sku,
                name=spec["name"],
                industry=pack["industry"],
                hs6=spec["hs6"],
                uom=spec["uom"],
                unit_value_usd=spec.get("unit_value_usd"),
                cold_chain=bool(spec.get("cold_chain", False)),
                shelf_life_days=spec.get("shelf_life_days"),
            )
            self.world.products[sku] = record
            self.world.add(record)
        for parent, components in pack["bom"].items():
            for component, qty in components.items():
                p, c = f"{prefix}-{parent}", f"{prefix}-{component}"
                self.world.add(
                    BomEdgeRecord(
                        id=self.rid("bom_edge", f"{p}>{c}"),
                        **self.lin(f"{p}>{c}"),
                        parent_product_id=self.world.products[p].id,
                        component_product_id=self.world.products[c].id,
                        qty_per_unit=float(qty),
                    )
                )

    def network(self, pack: dict[str, Any]) -> dict[str, list[str]]:
        """Organizations and facilities; returns product → facilities that make it."""
        industry = pack["industry"]
        prefix = INDUSTRY_PREFIX[industry]
        makers: dict[str, list[str]] = {}
        maker_org = {"garments": "garment_exporter", "pharma": "pharma_maker"}[industry]
        n_makers = 5 if industry == "garments" else 3
        for i in range(1, n_makers + 1):
            self.org(f"{maker_org}_{i}", OrgKind.MANUFACTURER, Industry(industry), "BD")
        for ftype, spec in pack["facilities"].items():
            if ftype == "overseas":
                continue
            kind = FacilityType(ftype)
            for i in range(1, spec["count"] + 1):
                cluster = spec["clusters"][(i - 1) % len(spec["clusters"])]
                if kind in (FacilityType.GARMENT_FACTORY, FacilityType.PHARMA_PLANT):
                    org_key = f"{maker_org}_{(i - 1) % n_makers + 1}"
                else:
                    org_key = f"{ftype}_{i}"
                    self.org(org_key, OrgKind.SUPPLIER, Industry(industry), "BD")
                key = f"{org_key}.{ftype}.{i}"
                facility = self.facility(
                    key, org_key, kind, cluster, {"lines": self.rng.randint(4, 24)}
                )
                for product in spec["makes"]:
                    makers.setdefault(f"{prefix}-{product}", []).append(facility.name_key or key)
        for spec in pack["facilities"].get("overseas", []):
            city = spec["city"]
            org_key = f"overseas_{industry}_{city}"
            country = self.clusters["overseas"][city]["country"]
            self.org(org_key, OrgKind.SUPPLIER, Industry(industry), country)
            ftype = (
                FacilityType.RAW_MATERIAL_SUPPLIER
                if industry == "garments"
                else FacilityType.API_MANUFACTURER
            )
            key = f"{org_key}.export.1"
            self.facility(key, org_key, ftype, city, {"export": True}, overseas=True)
            for product in spec["makes"]:
                makers.setdefault(f"{prefix}-{product}", []).append(key)
        return makers

    def lanes(self) -> dict[str, UUID]:
        """Inland corridor lanes between real nodes (rows from DS-PORT-05); estimates."""
        out: dict[str, UUID] = {}
        specs = [
            ("BDCGP", "BDKAM", TransportMode.ROAD, 245.0, 0.6),  # ORS: 244.8 km to Kamalapur
            ("BDCGP", "BDKAM", TransportMode.RAIL, 321.0, 1.3),
            ("BDCGP", "BDPGN", TransportMode.BARGE, 300.0, 2.5),
            ("BDMGL", "BDKAM", TransportMode.ROAD, 230.0, 0.6),  # via the Padma Bridge (Q-13)
        ]
        for origin, dest, mode, km, days in specs:
            key = f"{origin}->{dest}:{mode}"
            lane_id = self.rid("lane", key)
            self.world.add(
                LaneRecord(
                    id=lane_id,
                    **self.lin(key),
                    origin_location_id=location_id(origin),
                    dest_location_id=location_id(dest),
                    mode=mode,
                    distance_km=km,
                    typical_transit_d=days,
                )
            )
            out[key] = lane_id
        return out

    def supply_edges(self, pack: dict[str, Any], makers: dict[str, list[str]]) -> None:
        """Each domestic facility of this pack buys every BOM component of what it makes."""
        industry = pack["industry"]
        prefix = INDUSTRY_PREFIX[industry]
        lt = pack["lead_time_d"]
        overseas = {
            f"overseas_{industry}_{s['city']}" for s in pack["facilities"].get("overseas", [])
        }
        w = self.world
        for consumer_key, consumer in list(w.facilities.items()):
            org = w.orgs[consumer_key.split(".")[0]]
            spec = pack["facilities"].get(w.facility_types[consumer_key])
            if org.industry != industry or org.kind == OrgKind.BUYER or not isinstance(spec, dict):
                continue
            needed = {f"{prefix}-{c}": None for p in spec["makes"] for c in pack["bom"].get(p, {})}
            for component in needed:
                suppliers = [s for s in makers.get(component, []) if s != consumer_key]
                if not suppliers:
                    continue
                for supplier_key, share in self._choose_suppliers(
                    component, suppliers, consumer_key
                ):
                    imported = supplier_key.split(".")[0] in overseas
                    lead = lt["imported" if imported else "domestic"]
                    key = f"{supplier_key}>{consumer_key}:{component}"
                    unit_value = w.products[component].unit_value_usd or 0.0
                    w.edges.append(
                        SupplyEdgeRecord(
                            id=self.rid("supply_edge", key),
                            **self.lin(key),
                            from_facility_id=w.facilities[supplier_key].id,
                            to_facility_id=consumer.id,
                            product_id=w.products[component].id,
                            share=share,
                            lead_time_mean_d=round(self.rng.gauss(lead["mean"], lead["sd"] / 3), 1),
                            lead_time_sd_d=float(lead["sd"]),
                            mode=TransportMode.SEA if imported else TransportMode.ROAD,
                            cost_per_unit_usd=round(unit_value * self.rng.uniform(0.9, 1.1), 4),
                            confidence=1.0,
                            valid_from=(w.start - timedelta(days=365)).date(),
                        )
                    )
        w.add(
            *(
                e
                for e in w.edges
                if e.product_id in {p.id for s, p in w.products.items() if s.startswith(prefix)}
            )
        )

    def _choose_suppliers(
        self, component: str, suppliers: list[str], consumer_key: str
    ) -> list[tuple[str, float]]:
        """Shares that sum to 1. Two deliberate structures serve the golden path (01 §5):
        denim is concentrated on one domestic mill (C1's single point of failure, "Mill X"),
        and the Gazipur "Factory A" imports knit fabric through Chattogram."""
        rng = self.rng
        if component == "G-KNIT_FABRIC" and consumer_key == HERO_FACTORY:
            importer = next(
                (s for s in suppliers if s.startswith("overseas_garments_shaoxing")), None
            )
            domestic = [s for s in suppliers if s != importer]
            if importer and domestic:
                return [(importer, 0.6), (rng.choice(domestic), 0.4)]
        if component == "G-DENIM_FABRIC":
            hub = next((s for s in suppliers if s.startswith("fabric_mill_3.")), None)
            others = [s for s in suppliers if s != hub]
            if hub and others:
                share = round(rng.uniform(0.7, 0.85), 2)
                return [(hub, share), (rng.choice(others), round(1 - share, 2))]
        k = min(len(suppliers), rng.choice([1, 2, 2, 3]))
        picked = rng.sample(suppliers, k)
        weights = [rng.uniform(0.5, 1.5) for _ in picked]
        total = sum(weights)
        shares = [round(x / total, 2) for x in weights]
        shares[-1] = round(1 - sum(shares[:-1]), 2)
        return list(zip(picked, shares, strict=True))

    def buyers(self, pack: dict[str, Any]) -> list[dict[str, Any]]:
        industry = pack["industry"]
        out = []
        for i, spec in enumerate(pack["buyers"], start=1):
            org_key = f"buyer_{industry}_{i}"
            country = self.clusters["overseas"][spec["city"]]["country"]
            self.org(org_key, OrgKind.BUYER, Industry(industry), country)
            key = f"{org_key}.dc.1"
            facility = self.facility(
                key, org_key, FacilityType.CUSTOMER_SITE, spec["city"], {}, overseas=True
            )
            out.append({**spec, "org_key": org_key, "facility": facility})
        return out

    def orders_and_shipments(
        self, pack: dict[str, Any], buyers: list[dict[str, Any]], makers: dict[str, list[str]]
    ) -> None:
        w, rng = self.world, self.rng
        prefix = INDUSTRY_PREFIX[pack["industry"]]
        spec = pack["orders"]
        months = math.ceil((spec["horizon_d"] + 30) / 30)
        for buyer in buyers:
            for m in range(months):
                for _ in range(spec["per_buyer_per_month"]):
                    sku = f"{prefix}-{rng.choice(buyer['products'])}"
                    factory_key = rng.choice(makers[sku])
                    due = (
                        w.start - timedelta(days=30) + timedelta(days=m * 30 + rng.randint(0, 29))
                    ).date()
                    qty = float(round(rng.uniform(*spec["qty_pcs"]), -2))
                    days_to_due = (due - w.start.date()).days
                    status = (
                        OrderStatus.DELIVERED
                        if days_to_due < -20
                        else OrderStatus.SHIPPED
                        if days_to_due < 10
                        else OrderStatus.IN_PRODUCTION
                        if days_to_due < 40
                        else OrderStatus.OPEN
                    )
                    ref = f"PO-{prefix}{len(w.orders) + 1:04d}"
                    placed = datetime.combine(due - timedelta(days=90), time(9), UTC)
                    order = CustomerOrderRecord(
                        id=self.rid("customer_order", ref),
                        **self.lin(ref, available_at=placed),
                        reference=ref,
                        buyer_org_id=w.orgs[buyer["org_key"]].id,
                        product_id=w.products[sku].id,
                        facility_id=w.facilities[factory_key].id,
                        qty=qty,
                        due_date=due,
                        incoterm="FOB",
                        priority=rng.randint(1, 5),
                        status=status,
                        revenue_usd=round(qty * (w.products[sku].unit_value_usd or 0), 2),
                    )
                    w.orders.append(order)
                    w.add(order)
                    if (
                        status in (OrderStatus.SHIPPED, OrderStatus.IN_PRODUCTION)
                        and days_to_due <= 45
                    ):
                        self.shipment(order, factory_key, buyer, pack)

    def shipment(
        self,
        order: CustomerOrderRecord,
        factory_key: str,
        buyer: dict[str, Any],
        pack: dict[str, Any],
    ) -> None:
        w, rng = self.world, self.rng
        cluster = w.facility_cluster[factory_key]
        local = cluster in ("cepz", "kepz")
        inland = "local" if local else rng.choices(["road", "rail", "barge"], [0.55, 0.3, 0.15])[0]
        gateway = buyer["gateway"]
        via = list(buyer["via"])
        hops = ["BDCGP", *via, gateway]
        sea_h = [SEA_H.get((a, b), 120.0) for a, b in pairwise(hops)]
        total_h = INLAND_H[inland] + PORT_DWELL_H + sum(sea_h) + TRANSSHIP_DWELL_H * len(via) + 24.0
        eta = datetime.combine(order.due_date, time(12), UTC)
        dep = eta - timedelta(hours=total_h)
        ref = f"SHP-{order.reference[3:]}"
        shipment_id = self.rid("shipment", ref)
        factory = w.facilities[factory_key]
        legs: list[tuple[TransportMode, UUID, UUID, float]] = []
        if inland in ("rail", "barge"):
            icd = "BDKAM" if inland == "rail" else "BDPGN"
            legs.append((TransportMode.ROAD, factory.location_id, location_id(icd), 3.0))
            legs.append(
                (
                    TransportMode.RAIL if inland == "rail" else TransportMode.BARGE,
                    location_id(icd),
                    location_id("BDCGP"),
                    INLAND_H[inland],
                )
            )
        else:
            legs.append(
                (TransportMode.ROAD, factory.location_id, location_id("BDCGP"), INLAND_H[inland])
            )
        for (a, b), hours in zip(pairwise(hops), sea_h, strict=True):
            legs.append((TransportMode.SEA, location_id(a), location_id(b), hours))
        legs.append((TransportMode.ROAD, location_id(gateway), buyer["facility"].location_id, 24.0))
        status = ShipmentStatus.IN_TRANSIT if dep < w.start else ShipmentStatus.PLANNED
        record = ShipmentRecord(
            id=shipment_id,
            **self.lin(ref, available_at=dep - timedelta(days=7)),
            reference=ref,
            mode_chain=[leg[0] for leg in legs],
            origin_location_id=factory.location_id,
            dest_location_id=buyer["facility"].location_id,
            cargo_profile=CargoProfile.DRY_CONTAINER,
            planned_eta=eta,
            status=status,
        )
        w.shipments.append(record)
        w.add(
            record,
            ShipmentOrderRecord(
                id=self.rid("shipment_order", ref),
                **self.lin(ref),
                shipment_id=shipment_id,
                order_id=order.id,
                qty=order.qty,
            ),
        )
        t = dep
        for seq, (mode, origin, dest, hours) in enumerate(legs):
            if mode == TransportMode.SEA and seq > 0 and legs[seq - 1][0] != TransportMode.SEA:
                t += timedelta(hours=PORT_DWELL_H)
            elif mode == TransportMode.SEA:
                t += timedelta(hours=TRANSSHIP_DWELL_H)
            arr = t + timedelta(hours=hours)
            # Actual times are planned + noise; "done" only if the actual time is before now.
            noise = timedelta(hours=rng.uniform(-2, 10))
            done_dep, done_arr = t + noise < w.start, arr + noise < w.start
            w.add(
                ShipmentLegRecord(
                    id=self.rid("shipment_leg", f"{ref}:{seq}"),
                    **self.lin(f"{ref}:{seq}"),
                    shipment_id=shipment_id,
                    seq=seq,
                    mode=mode,
                    from_location_id=origin,
                    to_location_id=dest,
                    planned_dep=t,
                    planned_arr=arr,
                    actual_dep=t + noise if done_dep else None,
                    actual_arr=arr + noise if done_arr else None,
                )
            )
            for code, where, ts, done in (
                ("DEPA", origin, t, done_dep),
                ("ARRI", dest, arr, done_arr),
            ):
                classifiers = [EventClassifier.PLN] + ([EventClassifier.ACT] if done else [])
                for classifier in classifiers:
                    when = ts + noise if classifier == EventClassifier.ACT else ts
                    key = f"{ref}:{seq}:{code}:{classifier}"
                    w.add(
                        TransportEventRecord(
                            id=self.rid("transport_event", key),
                            **self.lin(
                                key,
                                available_at=min(when, w.start)
                                if classifier == EventClassifier.ACT
                                else dep - timedelta(days=7),
                            ),
                            shipment_id=shipment_id,
                            event_type=TransportEventType.TRANSPORT,
                            classifier=classifier,
                            event_code=code,
                            location_id=where,
                            event_ts=when,
                        )
                    )
            t = arr

    def inventory_and_batches(self, pack: dict[str, Any]) -> None:
        w, rng = self.world, self.rng
        prefix = INDUSTRY_PREFIX[pack["industry"]]
        pack_products = {p.id: s for s, p in w.products.items() if s.startswith(prefix)}
        edges = [e for e in w.edges if e.product_id in pack_products]
        by_id = {f.id: k for k, f in w.facilities.items()}
        for edge in edges:
            consumer_key = by_id[edge.to_facility_id]
            supplier_key = by_id[edge.from_facility_id]
            sku = pack_products[edge.product_id]
            prior_key = (
                "overseas"
                if supplier_key.startswith("overseas_")
                else w.facility_types[supplier_key]
            )
            prior = pack["defects"].get(prior_key)
            if prior is None:
                continue
            # Incoming-material lots over the last 30 days, inspected at AQL 2.5 (estimates).
            for d in range(0, 30, rng.randint(3, 6)):
                key = f"{supplier_key}>{consumer_key}:{sku}:{d}"
                batch_id = self.rid("batch", key)
                produced = w.start - timedelta(days=30 - d, hours=rng.uniform(0, 12))
                lot_size = rng.randint(30, 900)
                n, ac, re = _aql(lot_size)
                found, rate = _beta_binomial(n, prior["a"], prior["b"], rng)
                lot = f"LOT-{prefix}-{batch_id.hex[:8].upper()}"
                w.add(
                    BatchRecord(
                        id=batch_id,
                        **self.lin(lot, available_at=produced + timedelta(hours=6)),
                        lot_code=lot,
                        product_id=edge.product_id,
                        facility_id=edge.to_facility_id,
                        supplier_facility_id=edge.from_facility_id,
                        size_units=lot_size,
                        produced_at=produced,
                        status=BatchStatus.RELEASED if found <= ac else BatchStatus.QUARANTINE,
                        aql_level="II / AQL 2.5",
                        aql_result={
                            "sample_size": n,
                            "defects_found": found,
                            "accept": ac,
                            "reject": re,
                            "decision": "accept" if found <= ac else "reject",
                            "latent_defect_rate": round(rate, 4),
                        },
                    )
                )
        ts = w.start - timedelta(hours=1)
        seen: set[tuple[UUID, UUID]] = set()
        for edge in edges:
            pair = (edge.to_facility_id, edge.product_id)
            if pair in seen:
                continue
            seen.add(pair)
            usage = rng.uniform(200, 3000)
            cover = rng.uniform(4, 28)
            key = f"{by_id[edge.to_facility_id]}:{pack_products[edge.product_id]}"
            w.add(
                InventoryPositionRecord(
                    id=self.rid("inventory_position", f"{key}:{ts.date()}"),
                    **self.lin(key, available_at=ts),
                    facility_id=edge.to_facility_id,
                    product_id=edge.product_id,
                    ts=ts,
                    on_hand=round(usage * cover, 1),
                    on_order=round(usage * rng.uniform(5, 20), 1),
                    allocated=round(usage * rng.uniform(1, 4), 1),
                    safety_stock=round(usage * 7, 1),
                    reorder_point=round(usage * 12, 1),
                    days_of_cover=round(cover, 1),
                )
            )

    def logistics_orgs(self) -> None:
        for key, kind in (
            ("forwarder_1", OrgKind.LOGISTICS),
            ("forwarder_2", OrgKind.LOGISTICS),
            ("carrier_1", OrgKind.CARRIER),
            ("carrier_2", OrgKind.CARRIER),
        ):
            self.org(key, kind, None, "BD")


def build_world(
    scenario_key: str = "baseline",
    seed: int = 42,
    start: date = DEFAULT_START,
    industries: tuple[str, ...] = ("garments", "pharma"),
    definition: dict[str, Any] | None = None,
) -> World:
    b = WorldBuilder(scenario_key, seed, start)
    b.scenario(definition or {"name": scenario_key, "industries": list(industries)})
    b.lanes()
    b.logistics_orgs()
    for industry in industries:
        pack = _yaml("industry_packs", f"{industry}.yaml")
        b.products(pack)
        makers = b.network(pack)
        b.supply_edges(pack, makers)
        buyers = b.buyers(pack)
        b.orders_and_shipments(pack, buyers, makers)
        b.inventory_and_batches(pack)
    w = b.world
    denim = w.products.get("G-DENIM_FABRIC")
    w.hero = {
        "denim_hub_facility": next(
            (k for k in w.facilities if k.startswith("fabric_mill_3.")), None
        ),
        "denim_edges": [e.id for e in w.edges if denim is not None and e.product_id == denim.id],
    }
    return w
