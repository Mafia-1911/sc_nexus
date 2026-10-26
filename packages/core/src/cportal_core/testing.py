"""Test-database helpers shared by the packages' integration tests.

The test database (`CPORTAL_TEST_DATABASE_URL`, default `cportal_test` on localhost) is created
by `scripts/db-local.sh init` and by the compose `db` image. Tests reset it from scratch, so it
never pins a migration revision that no longer exists.
"""

from __future__ import annotations

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from cportal_core.paths import repo_root

TEST_URL = os.environ.get(
    "CPORTAL_TEST_DATABASE_URL",
    "postgresql+psycopg://cportal:cportal@localhost:5432/cportal_test",
)


def database_available(url: str = TEST_URL) -> bool:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        return True
    except OperationalError:
        return False
    finally:
        engine.dispose()


def alembic_config(url: str = TEST_URL) -> Config:
    cfg = Config(str(repo_root() / "db" / "alembic.ini"))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={url}"]})()
    return cfg


def reset_database(url: str = TEST_URL) -> None:
    """Drop everything and migrate to head."""
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    engine.dispose()
    command.upgrade(alembic_config(url), "head")
