"""C2 configuration: gazetteer, lexicon (config/c2/) and disruption priors (config/priors/)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import yaml
from cportal_core.paths import config_dir


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    kind: str
    locode: str | None
    country: str | None
    lat: float
    lon: float
    weight: float
    cluster: str | None
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class Config:
    places: tuple[Place, ...]
    types: dict[str, list[re.Pattern[str]]]
    topic: list[re.Pattern[str]]
    industry: dict[str, list[re.Pattern[str]]]
    resolved: list[re.Pattern[str]]
    reported: list[re.Pattern[str]]
    duration: list[re.Pattern[str]]
    magnitude: dict[str, re.Pattern[str]]
    priors: dict[str, Any]

    def prior(self, event_type: str) -> dict[str, float]:
        types = self.priors["types"]
        return {k: float(v) for k, v in types.get(event_type, types["OTHER"]).items()}

    def reliability(self, source_id: str) -> float:
        table = self.priors["source_reliability"]
        return float(table.get(source_id, table["default"]))


def _rx(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def _alias_pattern(aliases: list[str]) -> re.Pattern[str]:
    # Longest first, so "Chattogram port" wins over "Chattogram".
    alts = sorted((re.escape(a) for a in aliases), key=len, reverse=True)
    return re.compile(r"(?<![\w-])(" + "|".join(alts) + r")(?![\w-])", re.IGNORECASE)


@lru_cache(maxsize=1)
def load_config() -> Config:
    base = config_dir()
    gaz = yaml.safe_load((base / "c2" / "gazetteer.yaml").read_text())
    lex = yaml.safe_load((base / "c2" / "lexicon.yaml").read_text())
    priors = yaml.safe_load((base / "priors" / "disruptions.yaml").read_text())
    places = tuple(
        Place(
            id=key,
            name=spec["name"],
            kind=spec["kind"],
            locode=spec.get("locode"),
            country=spec.get("country"),
            lat=float(spec["lat"]),
            lon=float(spec["lon"]),
            weight=float(spec["weight"]),
            cluster=spec.get("cluster"),
            pattern=_alias_pattern(spec["aliases"]),
        )
        for key, spec in gaz["places"].items()
    )
    return Config(
        places=places,
        types={t: _rx(ps) for t, ps in lex["types"].items()},
        topic=_rx(lex["topic"]),
        industry={k: _rx(v) for k, v in lex["industry"].items()},
        resolved=_rx(lex["resolved"]),
        reported=_rx(lex["reported"]),
        duration=_rx(lex["duration"]),
        magnitude={k: re.compile(v, re.IGNORECASE) for k, v in lex["magnitude"].items()},
        priors=priors,
    )
