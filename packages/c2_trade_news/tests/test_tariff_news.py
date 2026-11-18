"""C2 → tariff_news (the Tariff Monitor's news): which articles count, and how they group.

Wider than disruption events on purpose: a US tariff on Indian textiles matters to Bangladeshi
exporters even though it touches no Bangladeshi place. Headlines below are the real ones fetched
on 2026-11-18 (first four) plus written test cases.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cportal_c2.tariff import extract_tariff
from cportal_c2.tariff_news import NewsArticle, build_tariff_news, is_tariff_news

T0 = datetime(2026, 11, 18, 8, tzinfo=UTC)


def art(i: int, title: str, hours: float = 0, outlet: str = "a.example") -> NewsArticle:
    return NewsArticle(
        f"00000000-0000-0000-0000-{i:012d}",
        title,
        None,
        f"https://{outlet}/{i}",
        outlet,
        T0 + timedelta(hours=hours),
        "live",
    )


@pytest.mark.parametrize(
    ("title", "keep"),
    [
        (
            "US tariff shock prompts Indian textile exporters to diversify markets, "
            "reduce US reliance",
            True,
        ),
        ("India-US trade deal signing to await Washington's new tariff architecture", True),
        ("Govt imposes 162.5% duty on bulk scotch imports despite UK trade pact", False),
        ("China to give more tariff relief to Canadian pork", False),
        ("Trump loosens Canada tariffs in bid to help Republican senator", False),
        ("US cuts reciprocal tariff on Bangladesh garments to 10 percent from 20 percent", True),
        ("NBR hikes import duty on cotton yarn to 10 percent in the budget", True),
        ("Chattogram port congestion eases as vessels berth", False),
    ],
)
def test_which_articles_are_tariff_news(title: str, keep: bool) -> None:
    s = extract_tariff(title)
    assert (s is not None and is_tariff_news(s)) is keep, title


def test_reports_of_one_move_group_into_one_story() -> None:
    stories = build_tariff_news(
        [
            art(
                1, "US cuts reciprocal tariff on Bangladesh garments to 10 percent from 20 percent"
            ),
            art(
                2,
                "US cuts reciprocal tariff on Bangladesh garments to 10 percent from 20 percent, "
                "exporters say",
                hours=6,
                outlet="b.example",
            ),
            art(
                3, "US tariff shock prompts Indian textile exporters to diversify markets", hours=8
            ),
        ]
    )
    by = {s.direction + ":" + ",".join(s.origins): s for s in stories}
    cut = by["cut:BGD"]
    assert cut.reports == 2 and cut.outlets == ["a.example", "b.example"]
    assert cut.first_published == T0 and cut.url == "https://a.example/1"
    assert (cut.rate_pct, cut.previous_pct) == (10.0, 20.0)
    assert len(stories) == 2


def test_the_same_move_weeks_apart_is_two_stories() -> None:
    stories = build_tariff_news(
        [
            art(1, "US cuts tariff on Bangladesh garments to 10 percent from 20 percent"),
            art(
                2,
                "US cuts tariff on Bangladesh garments to 10 percent from 20 percent",
                hours=24 * 20,
            ),
        ]
    )
    assert len(stories) == 2


def test_records_are_deterministic_and_real() -> None:
    a = build_tariff_news([art(1, "US raises tariff on Vietnamese apparel to 20 percent")])
    b = build_tariff_news([art(1, "US raises tariff on Vietnamese apparel to 20 percent")])
    assert [s.id for s in a] == [s.id for s in b]
    assert a[0].data_mode == "live" and not a[0].is_synthetic
    assert a[0].quote == "raises" and a[0].origins == ["VNM"]
