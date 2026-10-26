"""Scenario library (03 §4): the baseline world and the hero scenario (Q-09: cyclone + supplier
delay). A scenario = world + port DES (history and projection) + source twins + scenario events.

Times are relative to the scenario's `start` (the world's "now"). Rows after `start` would be
the future, so only DES *history* becomes port calls, snapshots and twin observations; the
projection is summarised as KPIs in `scenario_result` (with vs without the disruption, run on
common random numbers so the difference is the disruption's alone).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import yaml
from cportal_connectors.canonical import ParseContext, scenario_uuid
from cportal_core.enums import (
    Capability,
    CargoProfile,
    DisruptionType,
    EventClassifier,
    EventStatus,
    LinkMethod,
    PortCallMethod,
    PortCallStatus,
    ShipmentStatus,
    ShipTypeGroup,
    TransportEventType,
    TransportMode,
    VisitKind,
)
from cportal_core.ids import location_id, port_id, record_id, stable_id, vessel_id
from cportal_core.paths import config_dir
from cportal_core.schemas.records import (
    DisruptionEventRecord,
    EventEntityLinkRecord,
    PortCallRecord,
    PortCallStopRecord,
    PortStateSnapshotRecord,
    Record,
    ScenarioResultRecord,
    ShipmentLegRecord,
    ShipmentRecord,
    TransportEventRecord,
    VesselRecord,
    point,
)

from cportal_sim import twins
from cportal_sim.port_des import DesResult, DesVisit, simulate, state_at
from cportal_sim.world import World, build_world

GENERATOR = "cportal-sim/scenarios/0.1.0"
SNAPSHOT_EVERY_H = 6
AIS_GROUP = {
    "container": ShipTypeGroup.CONTAINER,
    "tanker": ShipTypeGroup.TANKER,
    "dry_bulk": ShipTypeGroup.DRY_BULK,
    "general_cargo": ShipTypeGroup.GENERAL_CARGO,
    "roro": ShipTypeGroup.RO_RO,
    "lighter": ShipTypeGroup.CARGO,
}


@dataclass
class ScenarioSpec:
    key: str
    name: str
    start: datetime
    seed: int
    history_days: int
    projection_days: int
    industries: list[str]
    raw: dict[str, Any]

    @property
    def cyclone(self) -> dict[str, Any] | None:
        spec = self.raw.get("cyclone")
        if not spec:
            return None
        landfall = self.start + timedelta(hours=spec["landfall_h"])
        before, after = spec["port_closure_h"]
        return {
            **spec,
            "landfall_ts": landfall,
            "alert_ts": self.start + timedelta(hours=spec["alert_issued_h"]),
            "closure": (landfall + timedelta(hours=before), landfall + timedelta(hours=after)),
            "event_id": 9_000_000 + int(stable_id("cyclone", self.key).int % 100_000),
        }


def load_scenario(key: str) -> ScenarioSpec:
    def read(name: str) -> dict[str, Any]:
        data: dict[str, Any] = yaml.safe_load(
            (config_dir() / "scenarios" / f"{name}.yaml").read_text("utf-8")
        )
        if parent := data.pop("extends", None):
            base = read(parent)
            base.update(data)
            data = base
        return data

    raw = read(key)
    return ScenarioSpec(
        key=raw["key"],
        name=raw["name"],
        start=datetime.combine(date.fromisoformat(str(raw["start"])), time(0), UTC),
        seed=int(raw["seed"]),
        history_days=int(raw["history_days"]),
        projection_days=int(raw["projection_days"]),
        industries=list(raw["industries"]),
        raw=raw,
    )


@dataclass
class ScenarioRun:
    spec: ScenarioSpec
    world: World
    des: DesResult
    baseline_des: DesResult | None
    records: list[Record] = field(default_factory=list)

    def by_table(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.records:
            counts[r.table] = counts.get(r.table, 0) + 1
        return counts


# --- ground truth from the DES ---------------------------------------------------------------


def des_truth(des: DesResult, key: str, now: datetime) -> list[Record]:
    """Port calls as the DES knows them (`method=sim`), cut at `now`: nothing from the future."""
    ctx = ParseContext.synthetic("sim", key, GENERATOR)
    ctg = port_id("BDCGP")
    out: list[Record] = []
    seen: set[int] = set()
    for v in des.visits:
        if v.arrive >= now or v.depart <= des.start:
            continue
        vid = vessel_id(None, v.vessel.mmsi, ctx.scenario_id)
        assert vid is not None
        if v.vessel.mmsi not in seen:
            seen.add(v.vessel.mmsi)
            out.append(_vessel_record(v, ctx))
        done = v.depart <= now
        berth_start = v.berth_start if v.berth_start and v.berth_start <= now else None
        berth_end = v.berth_end if v.berth_end and v.berth_end <= now else None
        leave = v.leave_anchorage if v.leave_anchorage <= now else None
        call_id = ctx.rid("port_call", f"des:{v.index}")
        berth_zone = (
            record_id("port_zone", "DS-PORT-07", f"BDCGP:berth:{v.berth_code}")
            if v.berth_code and berth_start
            else None
        )
        out.append(
            PortCallRecord(
                id=call_id,
                **ctx.lineage(f"des:{v.index}", available_at=v.depart if done else now),
                vessel_id=vid,
                port_id=ctg,
                status=PortCallStatus.COMPLETED if done else PortCallStatus.ACTIVE,
                visit_kind=VisitKind.BERTH_CALL if v.mode == "berth" else VisitKind.ANCHORAGE_ONLY,
                arrival_ts=v.arrive,
                anchorage_start_ts=v.arrive,
                anchorage_end_ts=leave,
                berth_start_ts=berth_start,
                berth_end_ts=berth_end,
                departure_ts=v.depart if done else None,
                waiting_h=round(v.waiting_h, 2) if leave else None,
                berth_h=round(v.berth_h, 2) if done and v.berth_h is not None else None,
                dwell_h=round(v.dwell_h, 2) if done else None,
                berth_zone_id=berth_zone,
                censored=not done,
                method=PortCallMethod.SIM,
                quality_flags=[] if done else ["censored"],
            )
        )
        out.append(
            PortCallStopRecord(
                id=ctx.rid("port_call_stop", f"des:{v.index}:0"),
                **ctx.lineage(f"des:{v.index}:0", available_at=leave or now),
                port_call_id=call_id,
                seq=0,
                cell_id=v.anchorage["id"],
                at_dock=False,
                geom=point(v.spot[1], v.spot[0]),
                start_ts=v.arrive,
                end_ts=leave,
            )
        )
    return out


def _vessel_record(v: DesVisit, ctx: ParseContext) -> VesselRecord:
    vid = vessel_id(None, v.vessel.mmsi, ctx.scenario_id)
    assert vid is not None
    return VesselRecord(
        id=vid,
        **ctx.lineage(v.vessel.mmsi),
        mmsi=v.vessel.mmsi,
        name=v.vessel.name,
        call_sign=v.vessel.callsign,
        ship_type_ais=v.vessel.ais_type,
        ship_type_group=AIS_GROUP.get(v.kind),
        loa_m=float(v.vessel.loa),
        beam_m=float(v.vessel.beam),
    )


def snapshots(des: DesResult, key: str, now: datetime) -> list[Record]:
    ctx = ParseContext.synthetic("sim", key, GENERATOR)
    out: list[Record] = []
    ts = des.start
    while ts <= now:
        state = state_at(des, ts)
        out.append(
            PortStateSnapshotRecord(
                id=ctx.rid("port_state_snapshot", f"BDCGP:{ts.isoformat()}"),
                **ctx.lineage(f"BDCGP:{ts.isoformat()}", available_at=ts),
                port_id=port_id("BDCGP"),
                ts=ts,
                **state,
            )
        )
        ts += timedelta(hours=SNAPSHOT_EVERY_H)
    return out


# --- scenario events -------------------------------------------------------------------------


def cyclone_stories(spec: ScenarioSpec, cyclone: dict[str, Any]) -> list[twins.Story]:
    name = f"Cyclone {cyclone['name']}"
    alert = cyclone["alert_ts"]
    place = ("Chattogram Port", 22.3, 91.8)
    themes = ("NATURAL_DISASTER_CYCLONE", "MARITIME", "PORT", "ECON_TRADE")
    rows = [
        (0, "harbourwire.example", "cyclone-syn-01-signal-raised",
         f"{name}: maritime ports told to hoist signals as storm nears the coast",
         "Ports were advised to raise warning signals as the depression intensified into a "
         "cyclone over the Bay of Bengal. (Synthetic article for a demonstration scenario.)"),
        (5, "deltatimes.example", "chattogram-suspends-operations-syn",
         f"Chattogram port suspends cargo handling ahead of {name}",
         "Cargo handling and lighterage at the outer anchorage will stop while the danger "
         "signal is up; operators expect a 36 to 48 hour halt. (Synthetic.)"),
        (9, "shippinglens.example", "vessels-leave-anchorage-syn",
         "Vessels ordered out of Chattogram outer anchorage as cyclone approaches",
         "Mother vessels and lighters were told to seek shelter; berthing schedules are "
         "being revised. (Synthetic.)"),
        (14, "bd-business-daily.example", "rmg-exporters-brace-syn",
         "Garment exporters brace for shipment delays as storm closes in",
         "Exporters in Gazipur and Narayanganj expect fabric deliveries and vessel bookings "
         "to slip by several days. (Synthetic; all companies fictional.)"),
    ]  # fmt: skip
    return [
        twins.Story(alert + timedelta(hours=h), outlet, slug, title, snippet, themes, place)
        for h, outlet, slug, title, snippet in rows
    ]


def supplier_incident(spec: ScenarioSpec, world: World, cyclone: dict[str, Any]) -> list[Record]:
    delay = spec.raw["supplier_delay"]
    ctx = ParseContext.synthetic("sim", spec.key, GENERATOR)
    facility = world.facilities[delay["facility_key"]]
    start = cyclone["landfall_ts"] + timedelta(hours=delay["starts_h"])
    event_id = ctx.rid("disruption_event", f"supplier:{delay['facility_key']}")
    days = float(delay["lead_time_extra_d"])
    return [
        DisruptionEventRecord(
            id=event_id,
            **ctx.lineage(f"supplier:{delay['facility_key']}", available_at=start),
            type=DisruptionType.SUPPLIER_INCIDENT,
            subtype="flooding_power_outage",
            title=f"{facility.name}: flooding and power outage after Cyclone {cyclone['name']}",
            summary=(
                f"Production stopped at {facility.name}; deliveries expected "
                f"{days:.0f} days late. (Synthetic scenario event; the firm is fictional.)"
            ),
            status=EventStatus.ONGOING,
            severity=0.7,
            confidence=0.8,
            start_est=start,
            duration_p50_h=days * 24,
            duration_p90_h=days * 24 * 1.6,
            country_iso3=["BGD"],
            first_seen=start,
            last_updated=start,
            external_ids={"scenario": spec.key},
        ),
        EventEntityLinkRecord(
            id=ctx.rid("event_entity_link", f"supplier:{delay['facility_key']}"),
            **ctx.lineage(f"supplier:{delay['facility_key']}:link", available_at=start),
            event_id=event_id,
            entity_type="facility",
            entity_id=facility.id,
            link_method=LinkMethod.MANUAL,
            link_confidence=1.0,
            impact_hint={"lead_time_extra_d": days},
        ),
    ]


def hero_inbound(
    spec: ScenarioSpec, world: World, des: DesResult, baseline: DesResult | None
) -> list[Record]:
    """The vessel carrying Factory A's fabric (01 §5 step 3): a container ship arriving just
    before the closure, linked to an inbound shipment from the Shaoxing supplier."""
    hero = spec.raw.get("hero")
    if not hero:
        return []
    ctx = ParseContext.synthetic("sim", spec.key, GENERATOR)
    # Golden path step 3: of the container ships arriving after "now" and before the closure
    # ends, the one whose berthing the disruption delays most (vs the same vessel, same random
    # numbers, without the disruption). Without a disruption: the first such arrival.
    cyclone = spec.cyclone
    horizon_end = cyclone["closure"][1] if cyclone else spec.start + timedelta(days=2)
    base_by_index = {v.index: v for v in (baseline.visits if baseline else [])}

    def delay_h(v: DesVisit) -> float:
        base = base_by_index.get(v.index)
        if not base or not base.berth_start or not v.berth_start:
            return 0.0
        return (v.berth_start - base.berth_start).total_seconds() / 3600

    candidates = sorted(
        (
            v
            for v in des.visits
            if v.kind == "container"
            and v.mode == "berth"
            and v.berth_start is not None
            and spec.start <= v.arrive < horizon_end
        ),
        key=lambda v: (-delay_h(v), v.arrive),
    )
    if not candidates:
        return []
    ship = candidates[0]
    vid = vessel_id(None, ship.vessel.mmsi, ctx.scenario_id)
    assert vid is not None
    factory = world.facilities[hero["factory_key"]]
    supplier = world.facilities[hero["inbound_from"]]
    ref = "SHP-IN-HERO-1"
    shipment_id = ctx.rid("shipment", ref)
    berth_end = ship.berth_end or ship.leave_anchorage
    eta = berth_end + timedelta(hours=48)  # discharge, customs, road to Gazipur (estimate)
    sgsin, ctg = location_id("SGSIN"), location_id("BDCGP")
    legs = [
        (TransportMode.SEA, supplier.location_id, sgsin, ship.arrive - timedelta(days=12),
         ship.arrive - timedelta(days=7), None),
        (TransportMode.SEA, sgsin, ctg, ship.arrive - timedelta(days=5), berth_end, vid),
        (TransportMode.ROAD, ctg, factory.location_id, berth_end + timedelta(hours=30), eta, None),
    ]  # fmt: skip
    out: list[Record] = [
        _vessel_record(ship, ctx),
        ShipmentRecord(
            id=shipment_id,
            **ctx.lineage(ref, available_at=spec.start - timedelta(days=14)),
            reference=ref,
            mode_chain=[leg[0] for leg in legs],
            origin_location_id=supplier.location_id,
            dest_location_id=factory.location_id,
            cargo_profile=CargoProfile.DRY_CONTAINER,
            planned_eta=eta,
            status=ShipmentStatus.IN_TRANSIT,
        ),
    ]
    for seq, (mode, origin, dest, dep, arr, leg_vessel) in enumerate(legs):
        out.append(
            ShipmentLegRecord(
                id=ctx.rid("shipment_leg", f"{ref}:{seq}"),
                **ctx.lineage(f"{ref}:{seq}"),
                shipment_id=shipment_id,
                seq=seq,
                mode=mode,
                from_location_id=origin,
                to_location_id=dest,
                vessel_id=leg_vessel,
                planned_dep=dep,
                planned_arr=arr,
                actual_dep=dep if dep < spec.start else None,
            )
        )
        for code, where, ts in (("DEPA", origin, dep), ("ARRI", dest, arr)):
            out.append(
                TransportEventRecord(
                    id=ctx.rid("transport_event", f"{ref}:{seq}:{code}"),
                    **ctx.lineage(
                        f"{ref}:{seq}:{code}", available_at=spec.start - timedelta(days=14)
                    ),
                    shipment_id=shipment_id,
                    event_type=TransportEventType.TRANSPORT,
                    classifier=EventClassifier.PLN,
                    event_code=code,
                    location_id=where,
                    event_ts=ts,
                    vessel_id=leg_vessel,
                )
            )
    world.hero |= {"inbound_shipment": shipment_id, "inbound_vessel_mmsi": ship.vessel.mmsi}
    if baseline is not None:
        base = next((v for v in baseline.visits if v.index == ship.index), None)
        if base and base.berth_start and ship.berth_start:
            world.hero["hero_berth_delay_h"] = round(
                (ship.berth_start - base.berth_start).total_seconds() / 3600, 1
            )
    return out


def projection_kpis(des: DesResult, start: datetime, end: datetime) -> dict[str, Any]:
    ocean = [v for v in des.visits if v.kind != "lighter" and start <= v.arrive < end]
    waits = sorted(v.waiting_h for v in ocean if v.mode == "berth")
    peak = 0
    ts = start
    while ts < end:
        state = state_at(des, ts)
        peak = max(peak, sum(state["queue_by_type"]["waiting_for_berth"].values()))
        ts += timedelta(hours=SNAPSHOT_EVERY_H)
    return {
        "window": [start.isoformat(), end.isoformat()],
        "ocean_arrivals": len(ocean),
        "mean_wait_h": round(statistics.mean(waits), 1) if waits else None,
        "p90_wait_h": round(waits[int(0.9 * (len(waits) - 1))], 1) if waits else None,
        "peak_waiting_for_berth": peak,
        "vessel_hours_at_port": round(sum(v.dwell_h for v in ocean), 1),
    }


# --- build ---------------------------------------------------------------------------------------


def build_scenario(key: str) -> ScenarioRun:
    spec = load_scenario(key)
    cyclone = spec.cyclone
    world = build_world(
        key,
        seed=spec.seed,
        start=spec.start.date(),
        industries=tuple(spec.industries),
        definition={k: v for k, v in spec.raw.items() if k not in ("version",)},
    )
    sim_start = spec.start - timedelta(days=spec.history_days)
    sim_end = spec.start + timedelta(days=spec.projection_days)
    closures = [cyclone["closure"]] if cyclone else []
    des = simulate(sim_start, sim_end, seed=spec.seed, closures=closures)
    baseline_des = simulate(sim_start, sim_end, seed=spec.seed) if cyclone else None
    run = ScenarioRun(spec, world, des, baseline_des)
    now = spec.start
    records = run.records
    records += world.records
    records += des_truth(des, key, now)
    records += snapshots(des, key, now)
    # Source twins: what each source would have reported up to `now`.
    records += twins.gfw_port_visits(des, key, until=now)
    records += twins.gfw_presence(des, key, until=now)
    records += twins.gfw_sar(des, key, until=now)
    records += twins.portwatch(des, key, until=now, cyclone=cyclone)
    records += twins.aisstream(des, key, hour=now - timedelta(hours=1))
    for point_name, lat, lon, marine in (
        ("ctg_port", 22.32, 91.77, False),
        ("ctg_anchorage", 22.04, 91.71, True),
    ):
        records += twins.open_meteo(
            key, point_name, lat, lon, start=now, hours=24 * 5, marine=marine,
            issued=now - timedelta(hours=1), cyclone=cyclone, seed=spec.seed,
        )  # fmt: skip
    if cyclone:
        stories = cyclone_stories(spec, cyclone)
        records += twins.gdacs(key, cyclone)
        records += twins.gdelt_gkg(key, stories)
        records += twins.rss(key, stories[:3])
        records += twins.reliefweb(
            key, stories[:1], disaster=f"Bangladesh: Cyclone {cyclone['name']}"
        )
        records += supplier_incident(spec, world, cyclone)
    records += hero_inbound(spec, world, des, baseline_des)
    # Projection KPIs (with vs without the disruption).
    ctx = ParseContext.synthetic("sim", key, GENERATOR)
    kpis = {"scenario": projection_kpis(des, now, sim_end)}
    if baseline_des is not None:
        kpis["without_disruption"] = projection_kpis(baseline_des, now, sim_end)
    kpis["hero"] = {k: str(v) for k, v in world.hero.items() if k != "denim_edges"}
    records.append(
        ScenarioResultRecord(
            id=ctx.rid("scenario_result", f"{key}:c4:port_projection"),
            **ctx.lineage(f"{key}:c4", available_at=now),
            run_scenario_id=scenario_uuid(key),
            capability=Capability.C4,
            kpis=kpis,
            artifacts={"generator": GENERATOR, "des": "cportal-sim/port_des/0.1.0"},
        )
    )
    return run
