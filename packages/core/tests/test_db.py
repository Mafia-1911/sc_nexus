"""Integration: migrations and the loader against a real PostGIS (skipped when none is up).

Uses CPORTAL_TEST_DATABASE_URL (default: the `cportal_test` database that
`scripts/db-local.sh init` and docker compose create).
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cportal_core.ids import location_id, port_id, record_id, vessel_id
from cportal_core.loader import upsert
from cportal_core.schemas.records import (
    AisPositionRecord,
    LocationRecord,
    PortCallRecord,
    PortRecord,
    VesselRecord,
    point,
)
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

URL = os.environ.get(
    "CPORTAL_TEST_DATABASE_URL",
    "postgresql+psycopg://cportal:cportal@localhost:5432/cportal_test",
)
REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def db() -> Iterator[Engine]:
    engine = create_engine(URL)
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
    except OperationalError:
        pytest.skip(f"no test database at {URL.split('@')[-1]}")
    # A clean slate every run, so the test DB never pins a revision that no longer exists.
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    cfg = Config(str(REPO / "db" / "alembic.ini"))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={URL}"]})()  # type: ignore[assignment]
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")  # the downgrade path works too
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


def _port_fixture() -> list[LocationRecord | PortRecord]:
    loc = LocationRecord(
        id=location_id("BDCGP"),
        source_id="DS-PORT-05",
        source_record_id="BDCGP",
        data_mode="replay",
        locode="BDCGP",
        name="Chittagong",
        country_iso2="BD",
        kind="seaport",
        geom=point(91.8, 22.3),
    )
    port = PortRecord(
        id=port_id("BDCGP"),
        source_id="DS-PORT-05",
        data_mode="replay",
        location_id=loc.id,
        locode="BDCGP",
        name="Chattogram",
        port_type="sea",
        tidal=True,
    )
    return [loc, port]


def test_upsert_is_idempotent_and_merges_sources(db: Engine) -> None:
    vid = vessel_id("9636345", None)
    assert vid is not None
    from_cpa = VesselRecord(
        id=vid,
        source_id="DS-PORT-07",
        data_mode="replay",
        imo="9636345",
        name="PRETTY MERAK",
        loa_m=170.0,
    )
    from_gfw = VesselRecord(
        id=vid,
        source_id="DS-AIS-02",
        data_mode="replay",
        imo="9636345",
        mmsi=636012345,
        flag_iso3="LBR",
    )
    t0 = dt.datetime(2025, 12, 29, tzinfo=dt.UTC)
    call = PortCallRecord(
        id=record_id("port_call", "DS-PORT-07", "2026-01-05:J/2:9636345"),
        source_id="DS-PORT-07",
        data_mode="replay",
        vessel_id=vid,
        port_id=port_id("BDCGP"),
        status="active",
        visit_kind="berth_call",
        arrival_ts=t0,
        anchorage_start_ts=t0,
        berth_start_ts=t0 + dt.timedelta(days=2),
        waiting_h=48.0,
        method="cpa_report",
        quality_flags=["date_precision_day"],
    )
    with Session(db) as s:
        upsert(s, [*_port_fixture(), from_cpa, call])
        upsert(s, [from_gfw, call])  # a second source and a repeat
        s.commit()
        row = s.execute(
            text("select name, loa_m, mmsi, flag_iso3 from vessel where imo = '9636345'")
        ).one()
        assert tuple(row) == ("PRETTY MERAK", 170.0, 636012345, "LBR")  # null never erases
        assert s.execute(text("select count(*) from port_call")).scalar() == 1
        geom = s.execute(text("select ST_AsText(geom) from location")).scalar()
        assert geom == "POINT(91.8 22.3)"


def test_latest_position_only_moves_forward(db: Engine) -> None:
    def pos(hour: int, lon: float) -> AisPositionRecord:
        return AisPositionRecord(
            id=record_id("ais_position_latest", "DS-AIS-01", "405000001"),
            source_id="DS-AIS-01",
            data_mode="live",
            mmsi=405000001,
            ts=dt.datetime(2026, 10, 26, hour, tzinfo=dt.UTC),
            geom=point(lon, 22.0),
        )

    with Session(db) as s:
        upsert(s, [pos(10, 91.70)])
        upsert(s, [pos(9, 91.10)])  # older: ignored
        s.commit()
        assert s.execute(text("select ST_X(geom) from ais_position_latest")).scalar() == 91.7
        upsert(s, [pos(11, 91.75)])
        s.commit()
        assert s.execute(text("select ST_X(geom) from ais_position_latest")).scalar() == 91.75


def test_database_enforces_lineage(db: Engine) -> None:
    with Session(db) as s, pytest.raises(IntegrityError, match="lineage_synthetic"):
        s.execute(
            text(
                "insert into holiday (date, kind, name, country_iso2, source_id, data_mode, "
                "is_synthetic) values ('2026-03-20', 'public', 'x', 'BD', 'sim', 'live', true)"
            )
        )
