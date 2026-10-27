"""Database side of C3: road edges (DS-GEO-01), emission factors (DS-GEO-05), route results."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from cportal_core.ids import location_id
from cportal_core.models import EmissionFactor, Location, RoadEdge, RouteOption, RouteRequest
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import LineString, MultiLineString
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from cportal_c3 import MODEL_VERSION
from cportal_c3.network import Edge, RoadNet
from cportal_c3.osm import RoadSegment
from cportal_c3.plan import Plan, Request
from cportal_c3.priors import Priors, load_priors

NS = uuid5(NAMESPACE_URL, "cportal/c3")
CHUNK = 2000


def save_edges(session: Session, segments: Iterable[RoadSegment], source_date: str) -> int:
    """Replace the road network with these segments (real OSM data, replayed from the extract)."""
    session.execute(delete(RoadEdge))
    batch: list[dict[str, Any]] = []
    written = 0
    for s in segments:
        batch.append(
            {
                "id": uuid5(NS, f"{s.way_id}:{s.u}:{s.v}"),
                "source_id": "DS-GEO-01",
                "source_record_id": f"way/{s.way_id}",
                "data_mode": "replay",
                "is_synthetic": False,
                "generator_version": f"geofabrik-{source_date}",
                "way_id": s.way_id,
                "u": s.u,
                "v": s.v,
                "length_m": s.length_m,
                "highway": s.highway,
                "oneway": s.oneway,
                "maxspeed_kmh": s.maxspeed_kmh,
                "name": (s.name or "")[:200] or None,
                "geom": from_shape(LineString(s.coords), srid=4326),
            }
        )
        if len(batch) >= CHUNK:
            session.execute(insert(RoadEdge), batch)
            written += len(batch)
            batch = []
    if batch:
        session.execute(insert(RoadEdge), batch)
        written += len(batch)
    return written


def load_net(session: Session, priors: Priors | None = None) -> RoadNet:
    priors = priors or load_priors()
    edges = [
        Edge(
            u=r.u,
            v=r.v,
            length_m=r.length_m,
            highway=r.highway,
            maxspeed_kmh=r.maxspeed_kmh,
            coords=tuple((float(c[0]), float(c[1])) for c in to_shape(r.geom).coords),
            oneway=r.oneway,
        )
        for r in session.scalars(select(RoadEdge))
    ]
    return RoadNet(edges, priors)


def network_stamp(session: Session) -> tuple[int, str]:
    count, newest = session.execute(select(func.count(), func.max(RoadEdge.updated_at))).one()
    return int(count), str(newest)


def factors(session: Session, priors: Priors | None = None) -> dict[str, dict[str, Any]]:
    """The DESNZ rows each mode uses, with id, source and year (C3-AC03 traceability)."""
    priors = priors or load_priors()
    out: dict[str, dict[str, Any]] = {}
    for key, spec in priors["emission_factors"].items():
        q = select(EmissionFactor).where(
            EmissionFactor.vehicle_class == spec["vehicle_class"],
            EmissionFactor.unit == "tonne.km",
        )
        if spec.get("fuel"):
            q = q.where(EmissionFactor.fuel == spec["fuel"])
        row = session.scalars(q.order_by(EmissionFactor.year.desc())).first()
        if row is None:
            raise LookupError(f"no emission factor for {key}: {spec['vehicle_class']}")
        out[key] = {
            "id": str(row.id),
            "label": f"{row.vehicle_class}{' · ' + row.fuel if row.fuel else ''}",
            "value": row.value,
            "year": row.year,
            "source": row.source_id,
            "note": spec.get("note"),
        }
    return out


def save(
    session: Session, req: Request, plans: list[Plan], sweeps: dict[str, Any], priors: Priors
) -> UUID:
    places = priors.places
    request_id = uuid5(
        NS,
        f"request:{req.origin}:{req.dest}:{req.depart.isoformat()}:{datetime.now(UTC).isoformat()}",
    )
    lineage = {
        "source_id": "c3",
        "data_mode": "replay",
        "is_synthetic": False,
        "generator_version": MODEL_VERSION,
    }
    session.add(
        RouteRequest(
            id=request_id,
            **lineage,
            origin_location_id=_location(session, req.origin, places),
            dest_location_id=_location(session, req.dest, places),
            cargo_profile="REEFER_2_8C" if req.reefer else "DRY_CONTAINER",
            deadline=req.deadline,
            constraints={
                "qty_teu": req.qty_teu,
                "max_transit_h": req.max_transit_h,
                "origin": req.origin,
                "dest": req.dest,
                "depart": req.depart.isoformat(),
            },
            weights={},
        )
    )
    session.flush()
    for i, p in enumerate(plans):
        lines = [LineString(leg.coords) for leg in p.legs if len(leg.coords) >= 2]
        session.add(
            RouteOption(
                id=uuid5(NS, f"{request_id}:{i}"),
                **lineage,
                request_id=request_id,
                legs=[leg.summary() for leg in p.legs]
                + [{"name": p.name, "departures": sweeps.get(p.name, [])}],
                geom=from_shape(MultiLineString(lines), srid=4326) if lines else None,
                time_p50_h=round(p.quantile(0.5), 2),
                time_p90_h=round(p.quantile(0.9), 2),
                cost_bdt=round(p.cost_bdt, 2),
                cost_usd=round(p.cost_bdt / float(priors["fx_bdt_per_usd"]), 2),
                co2e_kg=round(p.co2e_kg, 2),
                on_time_prob=p.on_time_prob,
                pareto_rank=p.pareto_rank,
                explanation=p.explanation,
            )
        )
    return request_id


def _location(session: Session, place: str, places: dict[str, dict[str, Any]]) -> UUID:
    """A place's location row: the UN/LOCODE row when it is a port or ICD, else C3's own point."""
    if len(place) == 5 and place.isupper():
        loc = location_id(place)
        if session.get(Location, loc) is not None:
            return loc
    loc = uuid5(NS, f"place:{place}")
    if session.get(Location, loc) is None:
        spec = places[place]
        from shapely.geometry import Point

        session.add(
            Location(
                id=loc,
                source_id="c3",
                data_mode="replay",
                is_synthetic=False,
                name=str(spec["name"]),
                kind="site",
                country_iso2="BD",
                cluster=place,
                geom=from_shape(Point(float(spec["lon"]), float(spec["lat"])), srid=4326),
            )
        )
        session.flush()
    return loc
