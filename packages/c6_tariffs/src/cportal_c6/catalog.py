"""What C6 covers: watched markets, origins and products (config/tariffs/, industry packs)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import Any

import yaml
from cportal_core.paths import config_dir


@dataclass(frozen=True)
class Product:
    hs6: str
    name: str
    industry: str
    key: str


@cache
def watchlist() -> dict[str, Any]:
    with (config_dir() / "tariffs" / "watchlist.yaml").open(encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    return data


@cache
def feeds() -> list[dict[str, Any]]:
    with (config_dir() / "tariffs" / "feeds.yaml").open(encoding="utf-8") as fh:
        data: list[dict[str, Any]] = yaml.safe_load(fh)["feeds"]
    return data


@cache
def products() -> tuple[Product, ...]:
    """One entry per HS6 code in the industry packs (the first product named wins)."""
    seen: dict[str, Product] = {}
    for pack in sorted((config_dir() / "industry_packs").glob("*.yaml")):
        doc = yaml.safe_load(pack.read_text(encoding="utf-8"))
        for key, p in (doc.get("products") or {}).items():
            hs6 = str(p.get("hs6") or "")
            if re.fullmatch(r"\d{6}", hs6) and hs6 not in seen:
                seen[hs6] = Product(hs6, p["name"], doc["industry"], key)
    return tuple(sorted(seen.values(), key=lambda p: (p.industry, p.hs6)))


def markets() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = watchlist()["markets"]
    return out


def origins() -> list[str]:
    return list(watchlist()["origins"])


def live_source(market: str) -> str | None:
    value = markets().get(market, {}).get("live")
    return str(value) if value else None


MFN_HISTORY = "DS-TRADE-04"


def has_preferences(market: str) -> bool:
    """Whether the data knows this market's preferences (FTAs, GSP, LDC access): a live
    schedule carries them; otherwise a `preferences` source must be named in the watchlist."""
    m = markets().get(market, {})
    return bool(m.get("live") or m.get("preferences"))


@cache
def country_names() -> dict[str, str]:
    with (config_dir() / "tariffs" / "countries.yaml").open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)["countries"]
    return {iso3: c["names"][0] for iso3, c in data.items()}
