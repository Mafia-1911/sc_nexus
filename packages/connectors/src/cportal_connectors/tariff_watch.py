"""What the C6 tariff connectors fetch: markets, origins and HS codes (config/tariffs/)."""

from __future__ import annotations

import re
from functools import cache
from typing import Any

import yaml
from cportal_core.paths import config_dir


@cache
def watchlist() -> dict[str, Any]:
    with (config_dir() / "tariffs" / "watchlist.yaml").open(encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    return data


@cache
def watched_hs6() -> tuple[str, ...]:
    """Every HS6 code in the industry packs (garments, pharma), sorted."""
    codes: set[str] = set()
    for pack in sorted((config_dir() / "industry_packs").glob("*.yaml")):
        codes |= set(re.findall(r'hs6:\s*"(\d{6})"', pack.read_text(encoding="utf-8")))
    return tuple(sorted(codes))


def watched_headings() -> tuple[str, ...]:
    return tuple(sorted({c[:4] for c in watched_hs6()}))


def next_heading(heading: str) -> str:
    """HTS exportList's `to` is exclusive: heading H is fetched as from=H, to=H+1."""
    return f"{int(heading) + 1:04d}"
