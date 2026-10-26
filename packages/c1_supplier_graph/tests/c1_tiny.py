"""A hand-made network small enough to reason about (C1 unit tests use only core records).

    O1 (overseas, sea via SGSIN and Chattogram) ──fabric 100%──▶ P2 ─┐
    M1 ──fabric 50%──▶ P1 ◀──fabric 50%── M2                          ├─▶ BDCGP ─▶ C1 (buyer DC)
    T1 ──labels 100%──▶ P1, P2 (the sole label source)               ─┘

A T-shirt needs fabric AND labels. P1 holds 10 days of fabric and 5 of labels; P2 holds 3 days
of fabric and 20 of labels. Suppliers have 30 % spare capacity.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4, uuid5

from cportal_core.schemas.records import (
    BomEdgeRecord,
    CustomerOrderRecord,
    FacilityRecord,
    InventoryPositionRecord,
    OrganizationRecord,
    ProductRecord,
    Record,
    SupplyEdgeRecord,
)

AS_OF = datetime(2026, 10, 26, tzinfo=UTC)
HORIZON = 120
SCENARIO = uuid4()
NS = UUID("6f1d2c1e-0c1a-4d6e-9f60-1c1e0c1a4d6e")
HEADROOM = 1.3


def rid(key: str) -> UUID:
    return uuid5(NS, key)


def lin(key: str) -> dict[str, object]:
    return {
        "id": rid(key),
        "source_id": "test",
        "data_mode": "synthetic",
        "is_synthetic": True,
        "scenario_id": SCENARIO,
        "generator_version": "tiny",
    }


def build() -> list[Record]:
    out: list[Record] = []
    orgs = {
        "maker": ("BD", "manufacturer"),
        "mill1": ("BD", "supplier"),
        "mill2": ("BD", "supplier"),
        "trims": ("BD", "supplier"),
        "overseas": ("CN", "supplier"),
        "buyer": ("NL", "buyer"),
    }
    for key, (country, kind) in orgs.items():
        out.append(
            OrganizationRecord(
                **lin(f"org:{key}"),
                name=f"Org {key}",
                name_key=key,
                country_iso2=country,
                kind=kind,
                industry="garments",
                is_fictional=True,
            )
        )
    facilities = {
        "P1": ("maker", "garment_factory", "gazipur"),
        "P2": ("maker", "garment_factory", "cepz"),
        "M1": ("mill1", "fabric_mill", "narayanganj"),
        "M2": ("mill2", "fabric_mill", "savar"),
        "T1": ("trims", "trims_supplier", "gazipur"),
        "O1": ("overseas", "raw_material_supplier", "shaoxing"),
        "C1": ("buyer", "customer_site", "rotterdam"),
    }
    for key, (org, ftype, cluster) in facilities.items():
        out.append(
            FacilityRecord(
                **lin(f"facility:{key}"),
                organization_id=rid(f"org:{org}"),
                name=key,
                facility_type=ftype,
                location_id=rid(f"location:{key}"),
                cluster=cluster,
                capacity={"headroom": HEADROOM},
            )
        )
    for sku, value in (("G-TEE", 5.0), ("G-FABRIC", 3.0), ("G-LABEL", 0.02)):
        out.append(
            ProductRecord(
                **lin(f"product:{sku}"), sku=sku, name=sku, industry="garments", uom="pcs",
                unit_value_usd=value,
            )
        )  # fmt: skip
    for parent, component, qty in (("G-TEE", "G-FABRIC", 0.2), ("G-TEE", "G-LABEL", 1.0)):
        out.append(
            BomEdgeRecord(
                **lin(f"bom:{parent}>{component}"),
                parent_product_id=rid(f"product:{parent}"),
                component_product_id=rid(f"product:{component}"),
                qty_per_unit=qty,
            )
        )
    orders = {"P1": (12_000.0, 40, 60_000.0), "P2": (24_000.0, 50, 120_000.0)}
    for plant, (qty, due_in, revenue) in orders.items():
        out.append(
            CustomerOrderRecord(
                **lin(f"order:{plant}"),
                reference=f"PO-{plant}",
                buyer_org_id=rid("org:buyer"),
                product_id=rid("product:G-TEE"),
                facility_id=rid(f"facility:{plant}"),
                qty=qty,
                due_date=AS_OF.date() + timedelta(days=due_in),
                status="open",
                revenue_usd=revenue,
            )
        )
    tee = {plant: qty / HORIZON for plant, (qty, _, _) in orders.items()}
    supplies = (
        ("M1", "P1", "G-FABRIC", 0.5, "road"),
        ("M2", "P1", "G-FABRIC", 0.5, "road"),
        ("O1", "P2", "G-FABRIC", 1.0, "sea"),
        ("T1", "P1", "G-LABEL", 1.0, "road"),
        ("T1", "P2", "G-LABEL", 1.0, "road"),
    )
    per_unit = {"G-FABRIC": 0.2, "G-LABEL": 1.0}
    for src, dst, sku, share, mode in supplies:
        need = tee[dst] * per_unit[sku]
        out.append(
            SupplyEdgeRecord(
                **lin(f"edge:{src}>{dst}:{sku}"),
                from_facility_id=rid(f"facility:{src}"),
                to_facility_id=rid(f"facility:{dst}"),
                product_id=rid(f"product:{sku}"),
                share=share,
                capacity_per_week=need * share * 7 * HEADROOM,
                lead_time_mean_d=21.0,
                mode=mode,
                valid_from=date(2025, 10, 26),
            )
        )
    cover = {
        ("P1", "G-FABRIC"): 10,
        ("P1", "G-LABEL"): 5,
        ("P2", "G-FABRIC"): 3,
        ("P2", "G-LABEL"): 20,
    }
    for (plant, sku), days in cover.items():
        out.append(
            InventoryPositionRecord(
                **lin(f"stock:{plant}:{sku}"),
                facility_id=rid(f"facility:{plant}"),
                product_id=rid(f"product:{sku}"),
                ts=AS_OF - timedelta(hours=1),
                on_hand=tee[plant] * per_unit[sku] * days,
            )
        )
    return out


def node(key: str) -> str:
    return str(rid(f"facility:{key}"))
