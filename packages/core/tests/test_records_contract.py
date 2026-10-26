"""Contract: every canonical record matches its ORM table (no DB needed)."""

from __future__ import annotations

import datetime as dt
import types
import typing
from typing import Any, get_args, get_origin
from uuid import UUID

import pytest
from cportal_core.enums import DataMode
from cportal_core.ids import entity_id, imo_check_digit_ok, mmsi_mid, normalize_locode, vessel_id
from cportal_core.models import LINEAGE_COLUMNS, Base
from cportal_core.schemas.records import (
    RECORD_TYPES,
    ArticleRecord,
    OrganizationRecord,
    PortCallRecord,
    Record,
    point,
)
from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from pydantic import AwareDatetime, ValidationError
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    SmallInteger,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

SCENARIO = UUID("00000000-0000-0000-0000-00000000beef")


def _base_type(annotation: Any) -> Any:
    """Strip Optional / Annotated to the core Python type."""
    origin = get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        return _base_type(args[0])
    if origin is typing.Annotated:
        return _base_type(get_args(annotation)[0])
    return origin or annotation


COMPATIBLE: dict[Any, tuple[type, ...]] = {
    str: (String, Text),
    int: (Integer, BigInteger, SmallInteger),
    float: (Float,),
    bool: (Boolean,),
    UUID: (Uuid,),
    dt.datetime: (DateTime,),
    AwareDatetime: (DateTime,),
    dt.date: (Date,),
    dict: (JSONB, Geometry),
    list: (JSONB, ARRAY),
}


@pytest.mark.parametrize("record_type", RECORD_TYPES, ids=lambda r: r.__name__)
def test_record_fields_match_table_columns(record_type: type[Record]) -> None:
    table = Base.metadata.tables[record_type.table]
    columns = set(table.c.keys())
    fields = record_type.model_fields
    unknown = set(fields) - columns
    assert not unknown, f"{record_type.__name__} fields not in {table.name}: {unknown}"
    for name, info in fields.items():
        expected = _base_type(info.annotation)
        if isinstance(expected, type) and issubclass(expected, str):
            expected = str  # StrEnum values are VARCHAR
        allowed = COMPATIBLE.get(expected)
        assert allowed, f"{record_type.__name__}.{name}: unmapped type {expected}"
        assert isinstance(table.c[name].type, allowed), (
            f"{record_type.__name__}.{name}: {expected} vs {table.c[name].type!r}"
        )
    # Every NOT NULL column without a default must be settable from the record.
    for column in table.c:
        if column.nullable or column.default is not None or column.server_default is not None:
            continue
        if column.name in LINEAGE_COLUMNS and column.name not in fields:
            continue
        if isinstance(column.type, Vector):
            continue
        assert column.name in fields, f"{table.name}.{column.name} is required but not in record"


def test_every_domain_table_has_lineage() -> None:
    infra = {"outbox_event", "job"}
    for table in Base.metadata.sorted_tables:
        if table.name in infra:
            continue
        missing = set(LINEAGE_COLUMNS) - set(table.c.keys())
        assert not missing, f"{table.name} lacks lineage columns {missing}"


def test_lineage_rules() -> None:
    ok = dict(id=SCENARIO, source_id="sim", url="https://x", url_canonical="https://x")
    ArticleRecord(
        **ok,
        data_mode=DataMode.SYNTHETIC,
        is_synthetic=True,
        scenario_id=SCENARIO,
        discovered_via="rss",
    )
    with pytest.raises(ValidationError, match="is_synthetic"):
        ArticleRecord(
            **ok,
            data_mode=DataMode.LIVE,
            is_synthetic=True,
            scenario_id=SCENARIO,
            discovered_via="rss",
        )
    with pytest.raises(ValidationError, match="scenario_id"):
        ArticleRecord(**ok, data_mode=DataMode.SYNTHETIC, is_synthetic=True, discovered_via="rss")


def test_snippet_is_clipped_to_300_chars() -> None:
    a = ArticleRecord(
        id=SCENARIO,
        source_id="DS-NEWS-03",
        data_mode="live",
        url="u",
        url_canonical="u",
        discovered_via="rss",
        snippet="x" * 1000,
    )
    assert a.snippet is not None and len(a.snippet) == 300


def test_synthetic_firms_must_be_fictional() -> None:
    base = dict(
        id=SCENARIO,
        source_id="sim",
        data_mode="synthetic",
        is_synthetic=True,
        scenario_id=SCENARIO,
        name="X",
        kind="manufacturer",
    )
    OrganizationRecord(**base, is_fictional=True)
    with pytest.raises(ValidationError, match="rule 3"):
        OrganizationRecord(**base, is_fictional=False)


def test_port_call_order_is_checked() -> None:
    t0 = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    base = dict(
        id=SCENARIO,
        source_id="sim",
        data_mode="live",
        vessel_id=SCENARIO,
        port_id=SCENARIO,
        status="completed",
        method="gfw",
    )
    PortCallRecord(**base, anchorage_start_ts=t0, berth_start_ts=t0 + dt.timedelta(hours=5))
    with pytest.raises(ValidationError, match="precedes"):
        PortCallRecord(**base, anchorage_start_ts=t0, berth_start_ts=t0 - dt.timedelta(hours=1))
    with pytest.raises(ValidationError, match=r"naive|timezone"):
        PortCallRecord(**base, arrival_ts=dt.datetime(2026, 1, 1))  # naive


def test_geojson_is_validated() -> None:
    assert point(91.8, 22.3) == {"type": "Point", "coordinates": [91.8, 22.3]}
    from cportal_core.schemas.records import LocationRecord

    base = dict(id=SCENARIO, source_id="DS-PORT-05", data_mode="replay", name="x", kind="city")
    LocationRecord(**base, geom=point(91.8, 22.3))
    with pytest.raises(ValidationError, match="out of range"):
        LocationRecord(**base, geom={"type": "Point", "coordinates": [22.3, 191.8]})


def test_identifiers() -> None:
    assert normalize_locode("BD CGP") == "BDCGP"
    assert normalize_locode("bd-mgl") == "BDMGL"
    assert normalize_locode("Chattogram") is None
    assert imo_check_digit_ok("9636345")  # PRETTY MERAK, CPA berthing report 2026-01-05
    assert not imo_check_digit_ok("9636346")
    assert mmsi_mid(405000123) == 405
    assert mmsi_mid(999000001) == 999
    assert mmsi_mid("12345") is None
    # Same IMO from any source → same vessel row; synthetic stays in its scenario.
    assert vessel_id("9636345", 1) == vessel_id("9636345", None)
    assert vessel_id("9636345", None) != vessel_id("9636345", None, SCENARIO)
    assert vessel_id(None, 405000123) == entity_id("vessel", "mmsi", 405000123)
