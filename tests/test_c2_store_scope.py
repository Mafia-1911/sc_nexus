"""C2 store: real events stay real (A-136). A loop variable in `write` shadowed its
`scenario_id` argument, so every real event written after an area-type event (flood, strike)
was stored as the last scenario's synthetic row and deleted by that scenario's next pass."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from cportal_c2.cluster import Mention, cluster
from cportal_c2.config import load_config
from cportal_c2.extract import extract
from cportal_c2.store import write
from cportal_core.db import session_scope
from cportal_core.enums import DataMode, DiscoveredVia
from cportal_core.loader import upsert
from cportal_core.models import DisruptionEvent
from cportal_core.schemas.records import ArticleRecord
from cportal_core.testing import TEST_URL, database_available, reset_database
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(not database_available(), reason="no test database")
T0 = datetime(2026, 11, 18, 6, tzinfo=UTC)


def _m(i: int, title: str, hours: int) -> Mention:
    x = extract(f"00000000-0000-0000-0000-{i:012d}", title, None, T0 + timedelta(hours=hours))
    return Mention(
        x,
        "DS-NEWS-03",
        f"o{i}.example",
        T0 + timedelta(hours=hours),
        f"https://o{i}.example/{i}",
        title,
        "live",
    )


def test_real_events_after_an_area_event_stay_real() -> None:
    reset_database()
    with session_scope(TEST_URL) as s:  # two scenarios, as in a seeded database
        for key in ("baseline", "cyclone"):
            s.execute(
                text(
                    "INSERT INTO scenario (id, key, name, definition, seed, is_baseline, source_id,"
                    " data_mode, is_synthetic) VALUES (gen_random_uuid(), :k, :k, '{}', 1, false,"
                    " 'sim', 'replay', false)"
                ),
                {"k": key},
            )
    titles = {
        1: "Flood waters halt garment factories in Gazipur",
        2: "US cuts tariff on Bangladesh garments to 10 percent from 20 percent, "
        "Chattogram exporters say",
    }
    with session_scope(TEST_URL) as s:
        upsert(
            s,
            [
                ArticleRecord(
                    id=UUID(f"00000000-0000-0000-0000-{i:012d}"),
                    source_id="DS-NEWS-03",
                    data_mode=DataMode.LIVE,
                    url=f"https://o{i}.example/{i}",
                    url_canonical=f"https://o{i}.example/{i}",
                    title=t,
                    discovered_via=DiscoveredVia.RSS,
                    published_at=T0,
                    available_at=T0,
                )
                for i, t in titles.items()
            ],
        )
    events = cluster(
        [
            _m(1, "Flood waters halt garment factories in Gazipur", 0),
            _m(
                2,
                "US cuts tariff on Bangladesh garments to 10 percent from 20 percent, "
                "Chattogram exporters say",
                2,
            ),
        ],
        load_config(),
    )
    assert {e.type for e in events} >= {"FLOOD", "TRADE_POLICY_SANCTION"}
    with session_scope(TEST_URL) as s:
        write(s, events, T0 - timedelta(days=14), load_config())
    with session_scope(TEST_URL) as s:
        rows = s.execute(
            select(DisruptionEvent.type, DisruptionEvent.scenario_id, DisruptionEvent.is_synthetic)
        ).all()
    assert rows and all(sid is None and not syn for _t, sid, syn in rows), rows
