"""C4 public API (02 §6): read the stored replay predictions for the Ports & Vessels page.

Reads only (C4 predictions are precomputed by `c4 train` / the worker), so every call stays well
inside the 300 ms budget.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from cportal_core.models import ModelVersion, PortCall, Prediction, Vessel
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, aliased

from cportal_c4.schemas import Band, QueueForecastOut, VesselInPortOut, VesselTrackOut

NOTE = (
    "Replay of real GFW port visits (CC BY-NC 4.0). GFW publishes a visit after it ends, so the "
    "latest complete picture is weeks old; each snapshot uses only what was known then."
)


def snapshots(session: Session, locode: str) -> list[datetime]:
    kind = "port_call_remaining"
    rows = session.scalars(
        select(Prediction.as_of)
        .where(
            Prediction.capability == "c4",
            Prediction.target_type == kind,
            Prediction.source_record_id.like(f"{locode}:%"),
        )
        .distinct()
        .order_by(Prediction.as_of)
    ).all()
    return list(rows)


def _pick(times: list[datetime], as_of: datetime | None) -> datetime | None:
    if not times:
        return None
    if as_of is None:
        return times[-1]
    earlier = [t for t in times if t <= as_of]
    return earlier[-1] if earlier else times[0]


def metrics(session: Session, locode: str) -> dict[str, Any]:
    rows = session.scalars(
        select(ModelVersion).where(
            ModelVersion.capability == "c4", ModelVersion.name.like(f"% ({locode})")
        )
    ).all()
    return {r.name.split(" ")[0]: r.metrics for r in rows}


def forecast(
    session: Session, locode: str, as_of: datetime | None = None
) -> QueueForecastOut | None:
    times = snapshots(session, locode)
    at = _pick(times, as_of)
    if at is None:
        return None
    row = session.scalar(
        select(Prediction).where(
            Prediction.capability == "c4",
            Prediction.target_type == "port_queue",
            Prediction.as_of == at,
            Prediction.source_record_id.like(f"{locode}:%"),
        )
    )
    params = row.dist_params if row else {}
    return QueueForecastOut(
        locode=locode,
        as_of=at,
        snapshots=times,
        history=[tuple(x) for x in params.get("history", [])],
        forecast=[tuple(x) for x in params.get("forecast", [])],
        metrics=metrics(session, locode),
    )


def _vessel(rem: Prediction, arr: Prediction | None, call: PortCall, v: Vessel) -> VesselInPortOut:
    q = rem.quantiles
    explain = arr.explanation if arr else {}
    base = explain.get("baseline")
    assert call.arrival_ts is not None
    return VesselInPortOut(
        call_id=call.id,
        vessel_id=v.id,
        mmsi=v.mmsi,
        name=v.name,
        ship_type=v.ship_type_group,
        flag=v.flag_iso3,
        arrival_ts=call.arrival_ts,
        elapsed_h=float(rem.explanation.get("elapsed_h", 0.0)),
        dwell_at_arrival=Band(**arr.quantiles) if arr else None,
        baseline_at_arrival=Band(p10=base[0], p50=base[1], p90=base[2]) if base else None,
        remaining=Band(**q),
        departure_p10=rem.as_of + timedelta(hours=q["p10"]),
        departure_p50=rem.as_of + timedelta(hours=q["p50"]),
        departure_p90=rem.as_of + timedelta(hours=q["p90"]),
        drivers=explain.get("drivers", []),
        actual_departure_ts=call.departure_ts,
        actual_dwell_h=call.dwell_h,
    )


def _query(where: Any) -> Any:
    rem, arr = aliased(Prediction), aliased(Prediction)
    return (
        select(rem, arr, PortCall, Vessel)
        .join(PortCall, PortCall.id == rem.target_id)
        .join(Vessel, Vessel.id == PortCall.vessel_id)
        .outerjoin(
            arr,
            and_(
                arr.capability == "c4",
                arr.target_type == "port_call",
                arr.target_id == rem.target_id,
            ),
        )
        .where(rem.capability == "c4", rem.target_type == "port_call_remaining", where(rem))
    )


def vessels(
    session: Session, locode: str, as_of: datetime | None = None
) -> tuple[datetime | None, list[VesselInPortOut]]:
    """Vessels in port at the snapshot, soonest expected departure first."""
    at = _pick(snapshots(session, locode), as_of)
    if at is None:
        return None, []
    rows = session.execute(
        _query(lambda p: and_(p.as_of == at, p.source_record_id.like(f"{locode}:%")))
    ).all()
    out = [_vessel(*r) for r in rows]
    out.sort(key=lambda x: x.departure_p50)
    return at, out


def track(
    session: Session, vessel_id: UUID, as_of: datetime | None = None
) -> VesselTrackOut | None:
    """The vessel's latest predicted call and how its departure estimate moved day by day."""
    call_id = session.scalar(
        select(Prediction.target_id)
        .join(PortCall, PortCall.id == Prediction.target_id)
        .where(
            Prediction.capability == "c4",
            Prediction.target_type == "port_call_remaining",
            PortCall.vessel_id == vessel_id,
            *([Prediction.as_of <= as_of] if as_of else []),
        )
        .order_by(Prediction.as_of.desc())
        .limit(1)
    )
    if call_id is None:
        return None
    rows = list(session.execute(_query(lambda p: p.target_id == call_id)).all())
    rows.sort(key=lambda r: r[0].as_of)
    views = [_vessel(*r) for r in rows]
    current = next((v for r, v in zip(rows, views, strict=True) if r[0].as_of == as_of), views[-1])
    updates = [
        {
            "as_of": r[0].as_of,
            "elapsed_h": v.elapsed_h,
            "departure_p10": v.departure_p10,
            "departure_p50": v.departure_p50,
            "departure_p90": v.departure_p90,
        }
        for r, v in zip(rows, views, strict=True)
    ]
    return VesselTrackOut(vessel=current, updates=updates)
