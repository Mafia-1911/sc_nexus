"""C5-AC04: AQL plans match the published tables; lot decisions follow the OC curve."""

from __future__ import annotations

import random

import pytest
from cportal_c5.aql import LETTERS, SAMPLE, code_letter, plan

# Table 2-A (normal, single) with arrows resolved: per letter A…R, (n, Ac) for each AQL,
# parsed from the ANSI/ASQ Z1.4 tables in CRAN AQLSchemes (AAZ14Single.R), not typed by hand.
PUBLISHED = {
    0.65: ([20, 20, 20, 20, 20, 20, 20, 80, 80, 125, 200, 315, 500, 800, 1250, 2000],
           [0, 0, 0, 0, 0, 0, 0, 1, 1, 2, 3, 5, 7, 10, 14, 21]),
    1.0: ([13, 13, 13, 13, 13, 13, 50, 50, 80, 125, 200, 315, 500, 800, 1250, 1250],
          [0, 0, 0, 0, 0, 0, 1, 1, 2, 3, 5, 7, 10, 14, 21, 21]),
    1.5: ([8, 8, 8, 8, 8, 32, 32, 50, 80, 125, 200, 315, 500, 800, 800, 800],
          [0, 0, 0, 0, 0, 1, 1, 2, 3, 5, 7, 10, 14, 21, 21, 21]),
    2.5: ([5, 5, 5, 5, 20, 20, 32, 50, 80, 125, 200, 315, 500, 500, 500, 500],
          [0, 0, 0, 0, 1, 1, 2, 3, 5, 7, 10, 14, 21, 21, 21, 21]),
    4.0: ([3, 3, 3, 13, 13, 20, 32, 50, 80, 125, 200, 315, 315, 315, 315, 315],
          [0, 0, 0, 1, 1, 2, 3, 5, 7, 10, 14, 21, 21, 21, 21, 21]),
    6.5: ([2, 2, 8, 8, 13, 20, 32, 50, 80, 125, 200, 200, 200, 200, 200, 200],
          [0, 0, 1, 1, 2, 3, 5, 7, 10, 14, 21, 21, 21, 21, 21, 21]),
}  # fmt: skip
# A lot size inside each code letter's general-level-II range (A … Q).
LOT_FOR_LETTER = dict(zip("ABCDEFGHJKLMNPQ", [5, 12, 20, 40, 70, 120, 200, 400, 1000,
                                               2000, 5000, 20_000, 100_000, 300_000, 900_000],
                          strict=True))  # fmt: skip


@pytest.mark.parametrize("aql", sorted(PUBLISHED))
def test_table_2a_matches_published_rows(aql: float) -> None:
    sizes, accepts = PUBLISHED[aql]
    for letter, lot in LOT_FOR_LETTER.items():
        i = LETTERS.index(letter)
        p = plan(10**7, aql) if letter == "R" else plan(lot, aql)
        assert p.letter == letter
        n = min(sizes[i], lot)
        assert (p.sample_size, p.accept, p.reject) == (n, accepts[i], accepts[i] + 1), letter


def test_code_letters_and_the_briefs_example() -> None:
    assert [code_letter(n) for n in (8, 9, 50, 51, 500, 501, 3200, 3201, 10_000, 500_001)] == [
        "A", "B", "D", "E", "H", "J", "K", "L", "L", "Q"
    ]  # fmt: skip
    assert code_letter(1000, "I") == "G" and code_letter(1000, "III") == "K"
    p = plan(5000, 2.5)  # C5 §6: lot 3,201–10,000 → L, n = 200, Ac 10 / Re 11
    assert (p.letter, p.sample_size, p.accept, p.reject) == ("L", 200, 10, 11)
    assert SAMPLE["L"] == 200
    # Arrows: 26–50 at AQL 2.5 points up to C (n 5, 0/1); 51–90 points down to F (n 20, 1/2).
    assert (plan(40, 2.5).plan_letter, plan(40, 2.5).sample_size) == ("C", 5)
    assert (plan(70, 2.5).plan_letter, plan(70, 2.5).sample_size, plan(70, 2.5).accept) == (
        "F", 20, 1
    )  # fmt: skip
    assert plan(3, 2.5).sample_size == 3  # n ≥ lot size → 100 % inspection


def test_lot_decisions_follow_the_oc_curve() -> None:
    """Simulated lots are accepted as often as the binomial OC curve says (±3 points)."""
    rng = random.Random(4)
    p = plan(2000, 2.5)  # K: n 125, Ac 7
    for rate in (0.01, 0.04, 0.06, 0.10):
        trials = 1500
        accepted = sum(
            p.decide(sum(rng.random() < rate for _ in range(p.sample_size))) == "accept"
            for _ in range(trials)
        )
        assert abs(accepted / trials - p.p_accept(rate)) < 0.03, rate
    assert p.p_accept(0.01) > 0.99 and p.p_accept(0.10) < 0.1
