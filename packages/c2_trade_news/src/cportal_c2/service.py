"""C2 public API (02 §6): turn the recent article window into grounded, deduplicated events."""

from __future__ import annotations

from datetime import datetime

from cportal_core.loader import upsert
from cportal_core.models import Article, DisruptionEvent, EventMention, Scenario, TariffNews
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cportal_c2.cluster import cluster
from cportal_c2.config import load_config
from cportal_c2.store import read_mentions, window_start, write
from cportal_c2.tariff_news import NewsArticle, build_tariff_news


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
    totals["tariff_news"] = write_tariff_news(session, now)
    for scenario in session.scalars(select(Scenario)):
        start = window_start(scenario.available_at, days)
        found = read_mentions(session, start, cfg, scenario.id)
        counts = write(session, cluster(found, cfg), start, cfg, scenario.id)
        totals["relevant_articles"] += len(found)
        for k, v in counts.items():
            totals[k] = totals.get(k, 0) + v
    return totals


TARIFF_NEWS_DAYS = 60


def write_tariff_news(session: Session, now: datetime | None = None) -> int:
    """Real articles of the last 60 days → tariff_news stories (the Tariff Monitor's feed).
    Replaces the window's stories, so a re-run writes the same rows."""
    since = window_start(now, TARIFF_NEWS_DAYS)
    rows = session.execute(
        select(Article.id, Article.title, Article.snippet, Article.url, Article.source_name,
               Article.published_at, Article.data_mode)
        .where(~Article.is_synthetic, Article.scenario_id.is_(None), Article.published_at >= since)
    ).all()  # fmt: skip
    articles = [
        NewsArticle(
            str(r.id), r.title, r.snippet, r.url, r.source_name, r.published_at, r.data_mode
        )
        for r in rows
        if r.published_at is not None
    ]
    events = dict(
        session.execute(
            select(EventMention.article_id, EventMention.event_id)
            .join(DisruptionEvent, DisruptionEvent.id == EventMention.event_id)
            .where(DisruptionEvent.scenario_id.is_(None))
        ).all()
    )
    records = build_tariff_news(articles, {str(a): str(e) for a, e in events.items()})
    session.execute(delete(TariffNews).where(TariffNews.first_published >= since))
    if records:
        upsert(session, records)
    return len(records)
