"""Request dependencies: DB session, scenario scope, and the meta builder."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from cportal_core.db import session_factory
from cportal_core.models import Scenario
from fastapi import Depends, HTTPException, Query
from sqlalchemy import ColumnElement, false, or_, select
from sqlalchemy.orm import Session

from cportal_api.schemas import Meta, ModeLabel


def get_session() -> Iterator[Session]:
    session = session_factory()()
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_session)]


def get_current_user() -> str:
    """Single-tenant hackathon build (02 §13); the seam for real auth later."""
    return "demo"


DHAKA = timezone(timedelta(hours=6))
Horizon = Literal["past", "now", "future", "scenario"]


def resolve_as_of(value: str | None, now: datetime | None = None) -> tuple[datetime, Horizon]:
    """Real-data view time: 'today' (default: now), 'yesterday', 'tomorrow' or 'YYYY-MM-DD',
    each the end of that day in Dhaka; 'now' is a nowcast (latest facts, estimated where the
    data lags), 'future' a forecast."""
    now = now or datetime.now(UTC)
    today = now.astimezone(DHAKA).date()
    v = (value or "today").strip().lower()
    if v == "today":
        return now, "now"
    if v == "yesterday":
        day = today - timedelta(days=1)
    elif v == "tomorrow":
        day = today + timedelta(days=1)
    else:
        try:
            day = date.fromisoformat(v)
        except ValueError as exc:
            raise HTTPException(
                422, f"day must be today, yesterday, tomorrow or a date: {v!r}"
            ) from exc
    end = datetime.combine(day, time(23, 59, 59), DHAKA).astimezone(UTC)
    if day == today:
        return now, "now"
    return end, "future" if day > today else "past"


@dataclass(frozen=True)
class Scope:
    """Which synthetic scenario to show next to the real (live/replay) rows, and, for real
    data, the moment to show it at (`as_of`, None in a scenario: it has its own clock)."""

    key: str | None
    scenario_id: UUID | None
    as_of: datetime | None = None
    horizon: Horizon = "now"

    def rows(self, model: Any) -> ColumnElement[bool]:
        """Real rows always; synthetic rows only from the selected scenario."""
        if self.scenario_id is None:
            return model.is_synthetic == false()
        return or_(model.is_synthetic == false(), model.scenario_id == self.scenario_id)


def get_scope(
    session: SessionDep,
    scenario: Annotated[
        str | None,
        Query(description="Scenario key for synthetic rows; omit for real data only"),
    ] = "baseline",
    day: Annotated[
        str | None,
        Query(description="Real data only: today (default), yesterday, tomorrow or YYYY-MM-DD"),
    ] = None,
) -> Scope:
    if not scenario:
        when, horizon = resolve_as_of(day)
        return Scope(None, None, when, horizon)
    found = session.scalar(select(Scenario.id).where(Scenario.key == scenario))
    if found is None:
        raise HTTPException(404, f"unknown scenario {scenario!r}")
    return Scope(scenario, found, None, "scenario")


ScopeDep = Annotated[Scope, Depends(get_scope)]


def meta(
    rows: Iterable[Any] = (),
    scope: Scope | None = None,
    *,
    model_version: str | None = None,
    note: str | None = None,
    as_of: datetime | None = None,
) -> Meta:
    """The badge: the single data mode behind the rows, or 'mixed' with the counts."""
    modes: Counter[str] = Counter()
    sources: set[str] = set()
    for row in rows:
        modes[str(row.data_mode)] += 1
        sources.add(str(row.source_id))
    label: ModeLabel = "none" if not modes else "mixed"
    if len(modes) == 1:
        label = cast(ModeLabel, next(iter(modes)))
    return Meta(
        mode=label,
        modes=dict(modes),
        sources=sorted(sources),
        as_of=as_of or datetime.now(UTC),
        scenario=scope.key if scope else None,
        horizon=scope.horizon if scope else None,
        model_version=model_version,
        note=note,
    )
