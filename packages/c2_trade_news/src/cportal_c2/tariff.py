"""Tariff signal from a news text (Q-25, fixes G-9): rules first, every field grounded.

What it reads: whether a tariff goes up, down or away (direction), who charges it (the importing
market), whose goods it hits (origins), the new and previous rate, the industry and an
effective date. Only a raise may feed buffer recommendations (store.py); a cut or an exemption
is news, not a disruption. The Tariff Monitor shows these as "announced" until the official
schedule (C6) shows the change.

Deliberately narrow: patterns cover the way trade news phrases tariff moves; anything else is
`direction = "unknown"`, never a guess.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

_KEYWORD = re.compile(r"\b(tariffs?|dut(?:y|ies)|levy|levies|duty-free)\b", re.I)
_NUM = r"(\d+(?:\.\d+)?)"
_PCT = rf"{_NUM}\s*(?:%|percent\b|per cent\b|pc\b)"
_TO_FROM = re.compile(rf"\bto\s+{_PCT}\s+from\s+{_PCT}", re.I)
_FROM_TO = re.compile(rf"\bfrom\s+{_NUM}\s*(?:%|percent|per cent)?\s+to\s+{_PCT}", re.I)
_ANY_PCT = re.compile(_PCT, re.I)
_ZERO = re.compile(r"\bzero\b(?:\s+\w+){0,2}\s+(?:tariffs?|dut(?:y|ies)|rate)", re.I)

# the importing market: who charges the duty
MARKETS: dict[str, str] = {
    "USA": r"\bU\.?S\.?(?!\w)|\bUnited States\b|\bWashington\b|\bTrump\b|\bUSTR\b|\bAmerican\b",
    "EUN": r"\bEU\b|\bE\.U\.|\bEuropean Union\b|\bBrussels\b|\bEuropean Commission\b",
    "GBR": r"\bUK\b|\bU\.K\.|\bBritain\b|\bBritish\b|\bUnited Kingdom\b",
    "JPN": r"\bJapan\b|\bTokyo\b",
    "CAN": r"\bCanada\b|\bOttawa\b",
    "BGD": r"\bNBR\b|\bDhaka\b|\bNational Board of Revenue\b",
}
# whose goods: the origins the monitor compares
ORIGINS: dict[str, str] = {
    "BGD": r"\bBangladesh(?:i)?\b",
    "CHN": r"\bChin(?:a|ese)\b",
    "IND": r"\bIndia(?:n)?\b",
    "VNM": r"\bViet ?nam(?:ese)?\b",
    "KHM": r"\bCambodia(?:n)?\b",
    "PAK": r"\bPakistan(?:i)?\b",
    "LKA": r"\bSri Lanka(?:n)?\b",
}
INDUSTRIES: dict[str, str] = {
    "garments": r"\b(garments?|apparel|clothing|knitwear|textiles?|yarn|cotton|denim|RMG)\b",
    "pharma": r"\b(pharma(?:ceuticals?)?|medicines?|drugs?|APIs?)\b",
}
_LOSE = re.compile(
    r"\b(los(?:e|es|ing)|loss of|end(?:s|ing)? of|withdraw\w*)\b.{0,30}"
    r"\b(duty-free|preferen\w+|GSP|EBA)",
    re.I,
)
_EXEMPT = re.compile(r"\b(exempt\w*|waiv\w+|duty-free)\b", re.I)
_CUT = re.compile(
    r"\b(cut(?:s|ting)?|lower(?:s|ed|ing)?|reduc(?:e|es|ed|ing)|slash\w*|eas(?:e|es|ed)"
    r"|scrap\w*|remov\w+|lift(?:s|ed)?|roll(?:s|ed)? back|halv\w+)\b",
    re.I,
)
_RAISE = re.compile(
    r"\b(impos\w+|hik\w+|rais(?:e|es|ed|ing)|increas\w+|levies|slap\w*|threat\w*"
    r"|doubl\w+|new tariffs?)\b",
    re.I,
)
_THREAT = re.compile(
    r"\b(?:[Tt]hreat\w*|[Ww]arns?|[Cc]onsider\w*|[Pp]lans?|[Mm]ulls?|[Pp]ropos\w+|could|may)\b"
)  # case-sensitive "may": the month May is not a threat
_EFFECTIVE = re.compile(r"\beffective\s+(?:from\s+)?([A-Z][a-z]+ \d{1,2}(?:, \d{4})?)")


class TariffSignal(BaseModel):
    direction: str  # raise | cut | exempt | unknown
    status: str = "announced"  # announced | threatened
    markets: list[str] = Field(default_factory=list)
    origins: list[str] = Field(default_factory=list)
    rate_pct: float | None = None
    previous_pct: float | None = None
    industries: list[str] = Field(default_factory=list)
    effective: str | None = None
    spans: dict[str, dict[str, Any]] = Field(default_factory=dict)


def _span(m: re.Match[str], group: int = 0) -> dict[str, Any]:
    return {"text": m.group(group), "start": m.start(group), "end": m.end(group)}


def _found(patterns: dict[str, str], text: str) -> list[tuple[int, str, re.Match[str]]]:
    out = []
    for code, pattern in patterns.items():
        if m := re.search(pattern, text):
            out.append((m.start(), code, m))
    return sorted(out, key=lambda t: t[0])


def extract_tariff(text: str) -> TariffSignal | None:
    """The tariff signal in a text, or None when the text is not about a tariff."""
    kw = _KEYWORD.search(text or "")
    if kw is None:
        return None
    spans: dict[str, dict[str, Any]] = {"keyword": _span(kw)}
    markets = _found(MARKETS, text)
    origins = [o for o in _found(ORIGINS, text) if o[1] not in {m[1] for m in markets}]
    if markets:
        spans["market"] = _span(markets[0][2])

    rate = previous = None
    if m := _TO_FROM.search(text):
        rate, previous = float(m.group(1)), float(m.group(2))
        spans["rate"] = _span(m)
    elif m := _FROM_TO.search(text):
        previous, rate = float(m.group(1)), float(m.group(2))
        spans["rate"] = _span(m)
    elif m := _ZERO.search(text):
        rate = 0.0
        spans["rate"] = _span(m)
    elif m := _ANY_PCT.search(text):
        rate = float(m.group(1))
        spans["rate"] = _span(m)

    direction = "unknown"
    if rate is not None and previous is not None and rate != previous:
        direction = "cut" if rate < previous else "raise"
    elif m := _LOSE.search(text):
        direction = "raise"
        spans["direction"] = _span(m, 1)
    elif (m := _EXEMPT.search(text)) or (rate == 0.0 and (m := _ZERO.search(text))):
        direction = "exempt"
        spans["direction"] = _span(m)
    elif m := _CUT.search(text):
        direction = "cut"
        spans["direction"] = _span(m)
    elif m := _RAISE.search(text):
        direction = "raise"
        spans["direction"] = _span(m)
    if (
        "direction" not in spans
        and direction in {"cut", "raise"}
        and (m := (_CUT if direction == "cut" else _RAISE).search(text))
    ):
        spans["direction"] = _span(m)

    effective = None
    if m := _EFFECTIVE.search(text):
        effective = m.group(1)
        spans["effective"] = _span(m, 1)
    industries = [k for k, p in INDUSTRIES.items() if re.search(p, text, re.I)]
    return TariffSignal(
        direction=direction,
        status="threatened" if _THREAT.search(text) else "announced",
        markets=[m[1] for m in markets],
        origins=[o[1] for o in origins],
        rate_pct=rate,
        previous_pct=previous,
        industries=industries,
        effective=effective,
        spans=spans,
    )
