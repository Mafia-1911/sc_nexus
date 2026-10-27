"""C2 public API (02 §6): turn the recent article window into grounded, deduplicated events."""

from __future__ import annotations

from datetime import datetime

from cportal_core.models import Scenario
from sqlalchemy import select
from sqlalchemy.orm import Session

from cportal_c2.cluster import cluster
from cportal_c2.config import load_config
from cportal_c2.store import read_mentions, window_start, write


def process(session: Session, now: datetime | None = None, days: int = 14) -> dict[str, int]:
    """Extract, cluster and store events: real articles of the last `days` days, then each
    scenario's synthetic articles around its start. Idempotent: the same window, the same
    events."""
    cfg = load_config()
    since = window_start(now, days)
    mentions = read_mentions(session, since, cfg)
    totals = {
        "relevant_articles": len(mentions),
        **write(session, cluster(mentions, cfg), since, cfg),
    }
    for scenario in session.scalars(select(Scenario)):
        start = window_start(scenario.available_at, days)
        found = read_mentions(session, start, cfg, scenario.id)
        counts = write(session, cluster(found, cfg), start, cfg, scenario.id)
        totals["relevant_articles"] += len(found)
        for k, v in counts.items():
            totals[k] = totals.get(k, 0) + v
    return totals
