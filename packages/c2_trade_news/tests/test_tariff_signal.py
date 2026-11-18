"""C2 tariff signal (Q-25 / G-9): direction, market, origin, rates, products, date from a headline.

Every field must quote its span in the text (grounded, ADR-017); a cut or an exemption must
never read as a raise, because only raises may feed buffer recommendations.
"""

from __future__ import annotations

import pytest
from cportal_c2.tariff import extract_tariff


def sig(text: str):  # type: ignore[no-untyped-def]
    s = extract_tariff(text)
    assert s is not None, text
    return s


def test_cut_with_old_and_new_rate() -> None:
    s = sig("US cuts reciprocal tariff on Bangladesh garments to 10 percent from 20 percent")
    assert s.direction == "cut"
    assert s.markets == ["USA"] and s.origins == ["BGD"]
    assert (s.rate_pct, s.previous_pct) == (10.0, 20.0)
    assert s.industries == ["garments"]


def test_from_to_order_also_reads() -> None:
    s = sig("Washington lowers the extra duty on apparel from Bangladesh from 20% to 10%")
    assert s.direction == "cut" and (s.rate_pct, s.previous_pct) == (10.0, 20.0)
    assert s.markets == ["USA"] and s.origins == ["BGD"]


def test_zero_additional_tariff_is_an_exemption() -> None:
    s = sig(
        "The United States' decision to apply a zero additional tariff rate to specified "
        "specialty pharmaceutical products from Bangladesh"
    )
    assert s.direction == "exempt" and s.rate_pct == 0.0
    assert s.markets == ["USA"] and s.industries == ["pharma"]


def test_imposition_is_a_raise() -> None:
    s = sig("EU imposes 25% anti-dumping duty on steel wire from China")
    assert s.direction == "raise" and s.rate_pct == 25.0
    assert s.markets == ["EUN"] and s.origins == ["CHN"]


def test_threat_is_a_raise_marked_threatened() -> None:
    s = sig("Trump threatens 50 percent tariff on goods from India")
    assert s.direction == "raise" and s.rate_pct == 50.0 and s.status == "threatened"
    assert s.markets == ["USA"] and s.origins == ["IND"]


def test_losing_duty_free_access_is_a_raise_not_an_exemption() -> None:
    s = sig("Bangladesh garments to lose duty-free access to the EU after LDC graduation")
    assert s.direction == "raise"
    assert s.markets == ["EUN"] and s.origins == ["BGD"]


def test_dhaka_import_duty_market_is_bangladesh() -> None:
    s = sig("NBR hikes import duty on cotton yarn to 10 percent in the budget")
    assert s.direction == "raise" and s.markets == ["BGD"] and s.rate_pct == 10.0
    assert s.industries == ["garments"]


def test_rates_decide_direction_over_words() -> None:
    # "revises" says nothing; the numbers do
    s = sig("UK revises tariff on knitwear from 12% to 9.6% for Bangladesh")
    assert s.direction == "cut" and s.markets == ["GBR"]


def test_effective_date_is_quoted() -> None:
    s = sig("US raises tariff on Vietnamese apparel to 20 percent, effective August 7, 2026")
    assert s.effective == "August 7, 2026"
    assert s.direction == "raise" and s.origins == ["VNM"]


def test_spans_quote_the_text() -> None:
    text = "US cuts reciprocal tariff on Bangladesh garments to 10 percent from 20 percent"
    s = sig(text)
    for span in s.spans.values():
        assert text[span["start"] : span["end"]] == span["text"]
    assert s.spans["direction"]["text"] == "cuts"


def test_talks_have_unknown_direction() -> None:
    s = sig("Tariff talks between Dhaka and Washington continue next week")
    assert s.direction == "unknown" and s.rate_pct is None


@pytest.mark.parametrize(
    "text",
    [
        "Sanctions on Russian oil tankers tighten",
        "Chattogram port congestion eases as vessels berth",
        "",
    ],
)
def test_no_tariff_no_signal(text: str) -> None:
    assert extract_tariff(text) is None


def test_the_month_may_is_not_a_threat() -> None:
    s = sig("UK cuts tariff on Bangladeshi knitwear to 0%, effective May 1, 2027")
    assert s.status == "announced" and s.effective == "May 1, 2027"


# --- in the C2 pipeline: extraction → event subtype → alert rule (G-9) ---------------------------

from datetime import UTC, datetime, timedelta  # noqa: E402

from cportal_c2.cluster import Mention, cluster  # noqa: E402
from cportal_c2.extract import extract  # noqa: E402
from cportal_c2.store import alertable  # noqa: E402

T0 = datetime(2026, 11, 18, 6, tzinfo=UTC)


def _mention(i: int, title: str, hours: int = 0) -> Mention:
    x = extract(f"a{i}", title, None, T0 + timedelta(hours=hours))
    return Mention(
        x,
        "DS-NEWS-03",
        f"outlet{i}",
        T0 + timedelta(hours=hours),
        f"https://o{i}/{i}",
        title,
        "replay",
    )


def test_extraction_carries_the_signal_for_trade_policy_news() -> None:
    x = extract(
        "a1",
        "US cuts reciprocal tariff on Bangladesh garments to 10 percent from 20 percent",
        None,
        T0,
    )
    assert x.event_type == "TRADE_POLICY_SANCTION"
    assert x.tariff is not None and x.tariff.direction == "cut"
    other = extract("a2", "Chattogram port operations suspended as cyclone nears", None, T0)
    assert other.tariff is None


def test_event_subtype_follows_the_newest_directional_report() -> None:
    # a report that does not say which way the tariff moves joins the story; the cut decides
    (e,) = cluster(
        [
            _mention(1, "US tariff on Bangladesh garments under review, Chattogram exporters say"),
            _mention(2, "US cuts tariff on Bangladesh garments to 10 percent from 20 percent", 5),
        ]
    )
    assert e.type == "TRADE_POLICY_SANCTION" and len(e.mentions) == 2
    assert e.subtype == "tariff_cut"


def test_opposite_moves_are_separate_stories() -> None:
    events = cluster(
        [
            _mention(1, "US raises tariff on Bangladesh garments to 20 percent, exporters say"),
            _mention(2, "US cuts tariff on Bangladesh garments to 10 percent from 20 percent", 5),
        ]
    )
    assert sorted(e.subtype or "" for e in events) == ["tariff_cut", "tariff_raise"]


def test_only_raises_and_other_trade_policy_can_raise_alerts() -> None:
    raise_ = cluster([_mention(1, "US raises tariff on Bangladesh garments to 37 percent")])[0]
    cut = cluster(
        [_mention(2, "US cuts tariff on Bangladesh garments to 10 percent from 20 percent")]
    )[0]
    exempt = cluster([_mention(3, "US exempts Bangladesh pharmaceutical products from tariff")])[0]
    assert raise_.subtype == "tariff_raise" and alertable(raise_)
    assert cut.subtype == "tariff_cut" and not alertable(cut)
    assert exempt.subtype == "tariff_exempt" and not alertable(exempt)


@pytest.mark.parametrize(
    "title",
    [
        "Bangladesh garments to lose duty-free access to the EU after LDC graduation",
        "NBR hikes import duty on cotton yarn to 10 percent in the budget",
        "EU GSP review: Bangladesh preferential access after graduation",
    ],
)
def test_preference_and_import_duty_news_is_trade_policy(title: str) -> None:
    assert extract("t", title, None, T0).event_type == "TRADE_POLICY_SANCTION"


def test_different_tariff_stories_are_different_events() -> None:
    events = cluster(
        [
            _mention(
                1, "US cuts reciprocal tariff on Bangladesh garments to 10 percent from 20 percent"
            ),
            _mention(
                2,
                "Bangladesh garments to lose duty-free access to the EU after LDC graduation",
                hours=10,
            ),
            _mention(
                3,
                "US cuts reciprocal tariff on Bangladesh garments to 10 pc, exporters say",
                hours=12,
            ),
        ]
    )
    assert sorted((e.subtype, len(e.mentions)) for e in events) == [
        ("tariff_cut", 2),
        ("tariff_raise", 1),
    ]


@pytest.mark.parametrize(
    ("title", "direction"),
    [
        # real headlines, 2026-11-18: the direction word must be about the tariff
        (
            "US tariff shock prompts Indian textile exporters to diversify markets, reduce US "
            "reliance",
            "raise",
        ),
        ("India-US trade deal signing to await Washington's new tariff architecture", "unknown"),
        ("US slaps new tariffs on Chinese steel", "raise"),
    ],
)
def test_direction_words_must_be_about_the_tariff(title: str, direction: str) -> None:
    assert sig(title).direction == direction
