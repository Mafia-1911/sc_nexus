"""Tariff news for the Tariff Monitor (Q-25): articles with a tariff signal, grouped into stories.

Which articles count (`is_tariff_news`): the signal names a market the monitor watches (or
Bangladesh, as importer or exporter), and a competitor origin it watches or one of the watched
industries. That keeps "US tariff shock for Indian textile exporters" and drops "tariff relief for
Canadian pork". Wider than C2's disruption events on purpose; the Disruption Radar is unchanged.

Stories: reports agreeing on market, direction, origins and rates within a week are one story.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from cportal_core.enums import DataMode
from cportal_core.ids import stable_id
from cportal_core.schemas.records import TariffNewsRecord

from cportal_c2 import RULES_VERSION
from cportal_c2.extract import article_text
from cportal_c2.tariff import TariffSignal, extract_tariff

SOURCE = "C2"
WATCHED_MARKETS = {"USA", "GBR", "EUN", "JPN", "CAN"}
WATCHED_ORIGINS = {"BGD", "VNM", "KHM", "IND", "CHN", "PAK", "LKA"}
STORY_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class NewsArticle:
    article_id: str
    title: str | None
    snippet: str | None
    url: str
    outlet: str | None
    published: datetime
    data_mode: str  # live | replay (real articles only)


def is_tariff_news(s: TariffSignal) -> bool:
    markets, origins = set(s.markets), set(s.origins)
    where = bool(markets & WATCHED_MARKETS) or "BGD" in markets or "BGD" in origins
    who = bool(origins & WATCHED_ORIGINS) or bool(s.industries)
    return where and who


def _key(s: TariffSignal) -> str:
    return "|".join(
        [
            ",".join(sorted(s.markets)),
            s.direction,
            ",".join(sorted(s.origins)),
            str(s.rate_pct),
            str(s.previous_pct),
        ]
    )[:200]


@dataclass
class _Story:
    key: str
    signal: TariffSignal
    articles: list[NewsArticle]


def build_tariff_news(
    articles: list[NewsArticle], events_by_article: dict[str, str] | None = None
) -> list[TariffNewsRecord]:
    """Stories from real articles, oldest report first; deterministic ids (first article)."""
    events_by_article = events_by_article or {}
    stories: list[_Story] = []
    for a in sorted(articles, key=lambda a: (a.published, a.article_id)):
        s = extract_tariff(article_text(a.title, a.snippet))
        if s is None or not is_tariff_news(s):
            continue
        key = _key(s)
        story = next(
            (
                st
                for st in reversed(stories)
                if st.key == key and a.published - st.articles[-1].published <= STORY_WINDOW
            ),
            None,
        )
        if story is None:
            stories.append(_Story(key, s, [a]))
        else:
            story.articles.append(a)
    out: list[TariffNewsRecord] = []
    for st in stories:
        first, last = st.articles[0], st.articles[-1]
        mode = DataMode.LIVE if any(a.data_mode == "live" for a in st.articles) else DataMode.REPLAY
        event = next(
            (
                events_by_article[a.article_id]
                for a in st.articles
                if a.article_id in events_by_article
            ),
            None,
        )
        quote = (st.signal.spans.get("direction") or {}).get("text")
        out.append(
            TariffNewsRecord(
                id=stable_id("tariff_news", first.article_id),
                source_id=SOURCE,
                source_record_id=first.article_id,
                data_mode=mode,
                generator_version=RULES_VERSION,
                available_at=first.published,
                story_key=st.key,
                article_ids=[a.article_id for a in st.articles],
                title=article_text(first.title, None),
                url=first.url,
                outlets=sorted({a.outlet for a in st.articles if a.outlet}),
                reports=len(st.articles),
                first_published=first.published,
                last_published=last.published,
                direction=st.signal.direction,
                status=st.signal.status,
                markets=st.signal.markets,
                origins=st.signal.origins,
                rate_pct=st.signal.rate_pct,
                previous_pct=st.signal.previous_pct,
                industries=st.signal.industries,
                effective=st.signal.effective,
                quote=quote,
                spans=st.signal.spans,
                event_id=event,  # type: ignore[arg-type]
            )
        )
    return out
