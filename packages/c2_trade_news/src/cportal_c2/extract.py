"""Grounded extraction (C2 §4, §5.2–5.4): rules and a gazetteer over title + snippet.

Every field carries the character span of the text it came from, so nothing is shown without
evidence (the grounding rule). The rules are the baseline; the local LLM (`llm.py`) may fill
the same schema for the top-K articles and must pass the same grounding check.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from cportal_c2.config import Config, Place, load_config

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAY_RX = re.compile(
    r"\b(?:from |on |since |until |till )?(" + "|".join(WEEKDAYS) + r")\b", re.I
)
RELATIVE_RX = re.compile(r"\b(today|tonight|yesterday|tomorrow)\b", re.I)


class Span(BaseModel):
    text: str
    start: int
    end: int


class PlaceHit(BaseModel):
    place_id: str
    name: str
    locode: str | None
    country: str | None
    kind: str
    span: Span


class Magnitude(BaseModel):
    metric: str
    value: float
    span: Span


class Extraction(BaseModel):
    """The C2 output schema for one article (C2 §4), with spans instead of [start, end]."""

    article_id: str
    text: str
    relevance: float
    is_supply_chain_disruption: bool
    event_type: str | None = None
    type_span: Span | None = None
    locations: list[PlaceHit] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    start: datetime | None = None
    start_span: Span | None = None
    duration_h: float | None = None
    duration_span: Span | None = None
    magnitude: list[Magnitude] = Field(default_factory=list)
    status: str = "reported"
    status_span: Span | None = None
    confidence: float = 0.0
    extractor: str = "rules"
    llm_agrees: bool | None = None  # the local LLM's second opinion, when asked
    ungrounded: int = 0

    @property
    def primary(self) -> PlaceHit | None:
        """The most specific, most relevant place mentioned."""
        if not self.locations:
            return None
        rank = {"port": 0, "icd": 1, "epz": 2, "land_port": 2, "corridor": 2, "district": 3,
                "hub": 3, "chokepoint": 3, "city": 4, "sea": 5, "country": 6}  # fmt: skip
        return min(self.locations, key=lambda p: (rank.get(p.kind, 9), p.span.start))


TAG_RX = re.compile(r"<[^>]+>")


def article_text(title: str | None, snippet: str | None) -> str:
    title = " ".join(TAG_RX.sub(" ", title or "").split())
    snippet = " ".join(TAG_RX.sub(" ", snippet or "").split())
    if not snippet or (snippet.lower().startswith(title.lower()[:40]) and title):
        return title or snippet
    return f"{title}. {snippet}" if title else snippet


def _span(m: re.Match[str], group: int = 0) -> Span:
    return Span(text=m.group(group), start=m.start(group), end=m.end(group))


def _first(patterns: list[re.Pattern[str]], text: str) -> re.Match[str] | None:
    hits = [m for p in patterns if (m := p.search(text))]
    return min(hits, key=lambda m: m.start()) if hits else None


def _places(cfg: Config, text: str) -> list[tuple[Place, Span]]:
    out: list[tuple[Place, Span]] = []
    taken: list[tuple[int, int]] = []
    for place in sorted(cfg.places, key=lambda p: -p.weight):
        for m in place.pattern.finditer(text):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue  # inside a longer, already-matched name
            taken.append((m.start(), m.end()))
            out.append((place, _span(m)))
            break
    return out


def _start(text: str, published: datetime | None) -> tuple[datetime | None, Span | None]:
    if published is None:
        return None, None
    if m := RELATIVE_RX.search(text):
        offset = {"today": 0, "tonight": 0, "yesterday": -1, "tomorrow": 1}[m.group(1).lower()]
        return published + timedelta(days=offset), _span(m)
    if m := WEEKDAY_RX.search(text):
        target = WEEKDAYS.index(m.group(1).lower())
        delta = (target - published.weekday()) % 7
        # Past tense is the common case in news ("on Sunday" = the last Sunday).
        future = re.search(
            r"\b(from|will|until|till|next)\b", text[max(0, m.start() - 30) : m.end()], re.I
        )
        days = delta if future else -((published.weekday() - target) % 7)
        return published + timedelta(days=days), _span(m)
    return None, None


def extract(
    article_id: str,
    title: str | None,
    snippet: str | None,
    published: datetime | None,
    cfg: Config | None = None,
) -> Extraction:
    cfg = cfg or load_config()
    text = article_text(title, snippet)
    places = _places(cfg, text)
    type_hits = {t: m for t, ps in cfg.types.items() if (m := _first(ps, text))}
    event_type: str | None = None
    type_span: Span | None = None
    if type_hits:
        # Earliest cue wins: headlines lead with what happened.
        event_type, m = min(type_hits.items(), key=lambda kv: kv[1].start())
        type_span = _span(m)
    topic_hits = sum(1 for p in cfg.topic if p.search(text))
    place_weight = max((p.weight for p, _ in places), default=0.0)
    relevance = round(
        0.45 * place_weight + 0.35 * (1.0 if event_type else 0.0) + 0.2 * min(1.0, topic_hits / 2),
        3,
    )
    start, start_span = _start(text, published)
    duration_h = None
    duration_span = None
    if m := _first(cfg.duration, text):
        duration_span = _span(m)
        if m.group(1) and m.group(1).isdigit():
            unit = {"hour": 1, "hr": 1, "day": 24, "week": 168}[m.group(2).lower()]
            duration_h = float(m.group(1)) * unit
    magnitude = [
        Magnitude(metric=metric, value=float(m.group(1).replace(",", "")), span=_span(m))
        for metric, rx in cfg.magnitude.items()
        if (m := rx.search(text))
    ]
    status, status_span = "ongoing", None
    if m := _first(cfg.resolved, text):
        status, status_span = "resolved", _span(m)
    elif m := _first(cfg.reported, text):
        status, status_span = "reported", _span(m)
    grounded = sum(x is not None for x in (type_span, start_span, duration_span)) + len(places)
    # A weak place alone (the country, the sea, a far hub or chokepoint) needs a logistics topic
    # word too: "Bangladesh Bank website offline" is not a supply-chain event.
    is_disruption = (
        event_type is not None and relevance >= 0.6 and (place_weight >= 0.8 or topic_hits >= 1)
    )
    return Extraction(
        article_id=article_id,
        text=text,
        relevance=relevance,
        is_supply_chain_disruption=is_disruption,
        event_type=event_type,
        type_span=type_span,
        locations=[
            PlaceHit(
                place_id=p.id, name=p.name, locode=p.locode, country=p.country, kind=p.kind, span=s
            )
            for p, s in places
        ],
        industries=sorted(k for k, ps in cfg.industry.items() if any(p.search(text) for p in ps)),
        start=start,
        start_span=start_span,
        duration_h=duration_h,
        duration_span=duration_span,
        magnitude=magnitude,
        status=status,
        status_span=status_span,
        confidence=round(min(0.9, 0.4 + 0.1 * grounded), 2) if is_disruption else 0.0,
    )
