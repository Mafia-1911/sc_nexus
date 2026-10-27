"""Mentions → events (C2 §5.5–5.6): incremental clustering, lifecycle, severity, confidence.

A mention joins an event of the same type at the same place (or within `RADIUS_KM`) last
updated within `WINDOW_H`; otherwise it starts one. Syndicated copies collapse because they
share type and place; distinct sources (by outlet) raise confidence, and a single source is
capped (C2 §11). Event ids are deterministic, so re-processing a window is idempotent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from cportal_c2.config import Config, load_config
from cportal_c2.extract import Extraction

WINDOW_H = 72
RADIUS_KM = 150
# A hazard and the port closures it causes are one story: they cluster together, and the event
# takes the hazard's type (the root cause).
HAZARD = ("CYCLONE_STORM", "FLOOD", "EARTHQUAKE_OTHER_NATURAL")
FAMILY = {t: "hazard" for t in (*HAZARD, "PORT_OPERATIONS_SUSPENDED")}
COARSE = ("country", "sea")
NS = uuid5(NAMESPACE_URL, "cportal/c2")


@dataclass(frozen=True)
class Mention:
    extraction: Extraction
    source_id: str
    outlet: str  # source name or domain: the unit of independence
    published: datetime
    url: str
    title: str
    data_mode: str


@dataclass
class Event:
    id: UUID
    type: str
    place_id: str
    mentions: list[Mention] = field(default_factory=list)
    title: str = ""
    summary: str = ""
    status: str = "reported"
    severity: float = 0.0
    confidence: float = 0.0
    start: datetime | None = None
    start_uncertainty_h: float = 12.0
    duration_p50_h: float = 0.0
    duration_p90_h: float = 0.0
    locodes: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    lon: float = 0.0
    lat: float = 0.0
    clusters: list[str] = field(default_factory=list)
    data_mode: str = "replay"

    @property
    def first_seen(self) -> datetime:
        return min(m.published for m in self.mentions)

    @property
    def last_updated(self) -> datetime:
        return max(m.published for m in self.mentions)

    @property
    def outlets(self) -> list[str]:
        return sorted({m.outlet for m in self.mentions})


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 6371 * 2 * math.asin(math.sqrt(h))


def cluster(mentions: list[Mention], cfg: Config | None = None) -> list[Event]:
    cfg = cfg or load_config()
    places = {p.id: p for p in cfg.places}
    events: list[Event] = []
    for m in sorted(mentions, key=lambda m: (m.published, m.extraction.article_id)):
        x = m.extraction
        if not x.is_supply_chain_disruption or x.event_type is None or x.primary is None:
            continue
        here = places[x.primary.place_id]
        family = FAMILY.get(x.event_type, x.event_type)
        match = None
        for e in reversed(events):
            if FAMILY.get(e.type, e.type) != family:
                continue
            if m.published - e.last_updated > timedelta(hours=WINDOW_H):
                continue
            there = places[e.place_id]
            near = (
                e.place_id == here.id
                or _km((here.lat, here.lon), (there.lat, there.lon)) <= RADIUS_KM
            )
            # "Bay of Bengal" or "Bangladesh" alone joins an event in the same country.
            coarse = (here.kind in COARSE or there.kind in COARSE) and here.country == there.country
            if near or coarse:
                match = e
                break
        if match is None:
            match = Event(
                id=uuid5(NS, f"{x.event_type}:{here.id}:{x.article_id}"),
                type=x.event_type,
                place_id=here.id,
            )
            events.append(match)
        match.mentions.append(m)
        if x.event_type in HAZARD and match.type not in HAZARD:
            match.type = x.event_type  # the root cause names the event
        if here.kind not in COARSE and places[match.place_id].kind in COARSE:
            match.place_id = here.id  # the most specific place locates it
    for e in events:
        score(e, cfg)
    return events


def score(e: Event, cfg: Config) -> None:
    places = {p.id: p for p in cfg.places}
    prior = cfg.prior(e.type)
    lead = max(e.mentions, key=lambda m: (m.extraction.relevance, -m.published.timestamp()))
    e.title = lead.title
    e.summary = lead.extraction.text[:600]
    latest = max(e.mentions, key=lambda m: m.published)
    e.status = latest.extraction.status
    starts = [m.extraction.start for m in e.mentions if m.extraction.start]
    e.start = min(starts) if starts else e.first_seen
    e.start_uncertainty_h = 24.0 if starts else 12.0
    durations = [m.extraction.duration_h for m in e.mentions if m.extraction.duration_h]
    e.duration_p50_h = max(durations) if durations else prior["p50_h"]
    e.duration_p90_h = max(prior["p90_h"], e.duration_p50_h * 1.6)
    hit_places = {h.place_id for m in e.mentions for h in m.extraction.locations}
    e.locodes = sorted({places[p].locode for p in hit_places if places[p].locode})  # type: ignore[misc]
    e.countries = sorted({places[p].country for p in hit_places if places[p].country})  # type: ignore[misc]
    e.clusters = sorted({places[p].cluster for p in hit_places if places[p].cluster})  # type: ignore[misc]
    here = places[e.place_id]
    e.lat, e.lon = here.lat, here.lon
    vessels = max(
        (g.value for m in e.mentions for g in m.extraction.magnitude if g.metric == "vessels"),
        default=0.0,
    )
    scope = max(places[p].weight for p in hit_places)
    e.severity = round(min(1.0, prior["severity"] * scope + (0.1 if vessels >= 20 else 0.0)), 3)
    # Independent outlets corroborate; copies from one outlet do not.
    best: dict[str, float] = {}
    for m in e.mentions:
        r = cfg.reliability(m.source_id) * m.extraction.confidence
        best[m.outlet] = max(best.get(m.outlet, 0.0), r)
    miss = 1.0
    for r in best.values():
        miss *= 1 - r
    confidence = 1 - miss
    if len(best) == 1:
        confidence = min(confidence, float(cfg.priors["single_source_cap"]))
    e.confidence = round(confidence, 3)
    modes = {m.data_mode for m in e.mentions}
    e.data_mode = "live" if "live" in modes else "replay" if "replay" in modes else "synthetic"
