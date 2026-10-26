"""Request dependencies: DB session, scenario scope, and the meta builder."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, cast
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


@dataclass(frozen=True)
class Scope:
    """Which synthetic scenario to show next to the real (live/replay) rows."""

    key: str | None
    scenario_id: UUID | None

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
) -> Scope:
    if not scenario:
        return Scope(None, None)
    found = session.scalar(select(Scenario.id).where(Scenario.key == scenario))
    if found is None:
        raise HTTPException(404, f"unknown scenario {scenario!r}")
    return Scope(scenario, found)


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
        model_version=model_version,
        note=note,
    )
