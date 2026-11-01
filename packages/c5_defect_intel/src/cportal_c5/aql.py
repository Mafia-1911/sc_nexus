"""ISO 2859-1 single sampling plans, normal inspection (C5 §6.1, C5-AC04).

Table 1 maps the lot size and inspection level to a code letter; Table 2-A gives, for each code
letter and AQL, a sample size n with acceptance (Ac) and rejection (Re = Ac + 1) numbers, or an
arrow to the first plan below (↓) or above (↑). Each AQL column runs ↓ … ↓, 0/1, ↑, ↓, 1/2, 2/3,
3/4, 5/6, 7/8, 10/11, 14/15, 21/22, ↑ …, starting where n × AQL % ≈ 13. Arrows are resolved
here, so a plan's sample size can differ from its letter's. The tables were checked against the
ANSI/ASQ Z1.4 tables (same values as ISO 2859-1 and MIL-STD-105E) as encoded in the CRAN package
AQLSchemes, and two published lookups (QIMA: K at AQL 1.0 → 3/4; MetricGate: J at 1.0 → 2/3);
the tests carry those rows. AQLs 0.65–6.5 only (the garment and pharma range).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import comb
from typing import Any

LETTERS = "ABCDEFGHJKLMNPQR"
SAMPLE = dict(
    zip(LETTERS, [2, 3, 5, 8, 13, 20, 32, 50, 80, 125, 200, 315, 500, 800, 1250, 2000], strict=True)
)
# Table 1: upper lot-size bound → code letters for general inspection levels I, II, III.
TABLE_1 = [
    (8, "A", "A", "B"), (15, "A", "B", "C"), (25, "B", "C", "D"), (50, "C", "D", "E"),
    (90, "C", "E", "F"), (150, "D", "F", "G"), (280, "E", "G", "H"), (500, "F", "H", "J"),
    (1200, "G", "J", "K"), (3200, "H", "K", "L"), (10_000, "J", "L", "M"),
    (35_000, "K", "M", "N"), (150_000, "L", "N", "P"), (500_000, "M", "P", "Q"),
    (10**12, "N", "Q", "R"),
]  # fmt: skip
LEVELS = {"I": 1, "II": 2, "III": 3}
# The code letter whose plan is 0/1, per AQL (%).
ZERO_ONE = {0.65: "F", 1.0: "E", 1.5: "D", 2.5: "C", 4.0: "B", 6.5: "A"}
PLANS = [(0, 1), None, None, (1, 2), (2, 3), (3, 4), (5, 6), (7, 8), (10, 11), (14, 15), (21, 22)]
UP, DOWN = "up", "down"


def code_letter(lot_size: int, level: str = "II") -> str:
    if lot_size < 2:
        raise ValueError("lot size must be at least 2")
    col = LEVELS[level]
    return str(next(row[col] for row in TABLE_1 if lot_size <= int(row[0])))


def _cell(letter: str, aql: float) -> tuple[int, int] | str:
    """Table 2-A cell: (Ac, Re) or an arrow."""
    if aql not in ZERO_ONE:
        raise ValueError(f"AQL {aql} not tabulated here (0.65, 1.0, 1.5, 2.5, 4.0, 6.5)")
    offset = LETTERS.index(letter) - LETTERS.index(ZERO_ONE[aql])
    if offset < 0:
        return DOWN
    if offset == 1:
        return UP
    if offset == 2:
        return DOWN
    if offset >= len(PLANS):
        return UP
    plan = PLANS[offset]
    assert plan is not None
    return plan


@dataclass(frozen=True)
class Plan:
    lot_size: int
    level: str
    aql: float
    letter: str  # from Table 1
    plan_letter: str  # after following arrows
    sample_size: int  # = lot size when the plan's sample is larger (100 % inspection)
    accept: int
    reject: int

    def decide(self, defects: int) -> str:
        return "accept" if defects <= self.accept else "reject"

    def p_accept(self, p: float) -> float:
        """Operating characteristic: P(accept) at a true defect rate p (binomial)."""
        n = self.sample_size
        return sum(comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(self.accept + 1))

    def as_dict(self) -> dict[str, Any]:
        return {
            "lot_size": self.lot_size,
            "level": self.level,
            "aql": self.aql,
            "code_letter": self.letter,
            "plan_letter": self.plan_letter,
            "sample_size": self.sample_size,
            "accept": self.accept,
            "reject": self.reject,
        }


def plan(lot_size: int, aql: float, level: str = "II") -> Plan:
    letter = code_letter(lot_size, level)
    current = letter
    cell = _cell(current, aql)
    while isinstance(cell, str):
        step = 1 if cell == DOWN else -1
        current = LETTERS[LETTERS.index(current) + step]
        cell = _cell(current, aql)
    ac, re = cell
    n = min(SAMPLE[current], lot_size)  # "if n ≥ lot size, inspect 100 %"
    return Plan(lot_size, level, aql, letter, current, n, ac, re)
