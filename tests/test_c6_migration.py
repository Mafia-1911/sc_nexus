"""The C6 migrations upgrade a database that already holds tariff rows (A-135): a NOT NULL
column added to a filled table needs a server default, or every deployed database fails."""

from __future__ import annotations

import pytest
from alembic import command
from cportal_core.testing import TEST_URL, alembic_config, database_available, reset_database
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.skipif(not database_available(), reason="no test database")


def test_ceiling_column_upgrade_keeps_existing_rows() -> None:
    eng = create_engine(TEST_URL)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
        c.execute(
            text("CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS vector")
        )
    cfg = alembic_config(TEST_URL)
    command.upgrade(cfg, "d4dfca106281")  # the first C6 revision, before is_ceiling
    with eng.begin() as c:
        c.execute(
            text(
                "INSERT INTO tariff_effective_rate (as_of, market_iso3, hs6, origin_iso3,"
                " is_resolved,"
                " n_lines, is_stale, components, lines, notes, sources, computed_at, source_id,"
                " data_mode, is_synthetic) VALUES ('2026-11-18', 'CAN', '610910', 'BGD', true, 1,"
                " true, '[]', '[]', '[]', '[]', now(), 'C6', 'replay', false)"
            )
        )
    command.upgrade(cfg, "head")
    with eng.begin() as c:
        rows = c.execute(text("SELECT market_iso3, is_ceiling FROM tariff_effective_rate")).all()
    assert rows == [("CAN", False)]
    eng.dispose()
    reset_database()  # leave a clean head schema for the next module
