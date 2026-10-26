"""Load canonical records into Postgres: idempotent upserts keyed on the deterministic id.

Re-running an ingest or a seed updates rows in place. On conflict, a non-null incoming value
wins and a null never erases a known one (`coalesce`), so sources that know different fields of
the same vessel or port enrich one row instead of fighting over it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from geoalchemy2 import Geometry
from geoalchemy2.shape import from_shape
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from sqlalchemy import Table, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from cportal_core.models import Base
from cportal_core.schemas.records import Record

CHUNK = 500
# Never touched on update: identity and first-seen bookkeeping.
KEEP_ON_UPDATE = {"id", "created_at", "ingested_at"}
# Tables whose rows only move forward in time (latest-position semantics).
NEWER_ONLY = {"ais_position_latest": "ts"}


def table_for(record_type: type[Record] | Record) -> Table:
    return Base.metadata.tables[record_type.table]


def _geometry(value: dict[str, Any], column_type: Geometry) -> Any:
    geom: BaseGeometry = shape(value)
    kind = (column_type.geometry_type or "GEOMETRY").upper()
    if kind == "MULTIPOLYGON" and isinstance(geom, Polygon):
        geom = MultiPolygon([geom])
    elif kind == "MULTILINESTRING" and isinstance(geom, LineString):
        geom = MultiLineString([geom])
    return from_shape(geom, srid=4326)


def to_row(record: Record, table: Table) -> dict[str, Any]:
    row = record.row()
    for name in record.geometry_fields:
        value = row.get(name)
        column_type = table.c[name].type
        if value is not None and isinstance(column_type, Geometry):
            row[name] = _geometry(value, column_type)
    return row


def upsert(session: Session, records: Iterable[Record]) -> dict[str, int]:
    """Upsert records grouped by table, in dependency order. Returns rows written per table."""
    by_table: dict[str, list[Record]] = defaultdict(list)
    for record in records:
        by_table[record.table].append(record)
    order = [t.name for t in Base.metadata.sorted_tables]
    counts: dict[str, int] = {}
    for name in sorted(by_table, key=order.index):
        table = Base.metadata.tables[name]
        rows = [to_row(r, table) for r in by_table[name]]
        counts[name] = _upsert_rows(session, table, rows)
    return counts


def _upsert_rows(session: Session, table: Table, rows: Sequence[dict[str, Any]]) -> int:
    # The last occurrence of an id wins within one call (Postgres rejects duplicate keys
    # inside a single INSERT … ON CONFLICT).
    unique = list({row["id"]: row for row in rows}.values())
    written = 0
    for start in range(0, len(unique), CHUNK):
        chunk = unique[start : start + CHUNK]
        stmt = insert(table).values(chunk)
        columns = set().union(*(row.keys() for row in chunk)) - KEEP_ON_UPDATE
        update: dict[str, Any] = {c: func.coalesce(stmt.excluded[c], table.c[c]) for c in columns}
        if "updated_at" in table.c:
            update["updated_at"] = func.now()
        where = None
        if newer := NEWER_ONLY.get(table.name):
            where = table.c[newer] < stmt.excluded[newer]
        stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=update, where=where)
        session.execute(stmt)
        written += len(chunk)
    return written
