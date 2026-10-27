"""C2 on hand-written headlines: grounded rules, clustering, confidence, LLM grounding."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cportal_c2.cluster import Mention, cluster
from cportal_c2.extract import extract
from cportal_c2.llm import apply, ground

TUESDAY = datetime(2026, 10, 27, 9, tzinfo=UTC)


def mention(
    i: int, title: str, snippet: str | None = None, outlet: str = "a.example", hours: float = 0
) -> Mention:
    published = TUESDAY + timedelta(hours=hours)
    x = extract(f"00000000-0000-0000-0000-{i:012d}", title, snippet, published)
    return Mention(x, "DS-NEWS-03", outlet, published, f"https://{outlet}/{i}", title, "replay")


def test_grounded_port_suspension() -> None:
    x = extract(
        "a",
        "Chattogram port operations suspended as cyclone signal hoisted",
        "Over 40 vessels moved out of the outer anchorage on Sunday, officials said.",
        TUESDAY,
    )
    assert x.is_supply_chain_disruption and x.event_type == "PORT_OPERATIONS_SUSPENDED"
    assert x.primary is not None and x.primary.locode == "BDCGP"
    # Every span quotes the text exactly (the grounding rule).
    for span in [x.type_span, x.start_span, *[p.span for p in x.locations]]:
        assert span is not None and x.text[span.start : span.end] == span.text
    assert (
        x.start is not None and x.start.date() == (TUESDAY - timedelta(days=2)).date()
    )  # last Sunday
    assert [(m.metric, m.value) for m in x.magnitude] == [("vessels", 40.0)]
    assert x.status == "ongoing"  # "suspended" is not "ended"


def test_strike_duration_and_future_start() -> None:
    x = extract(
        "b",
        "Transport workers call 48-hour strike on Dhaka-Chattogram highway from Thursday",
        None,
        TUESDAY,
    )
    assert x.event_type == "LABOR_STRIKE_BLOCKADE" and x.duration_h == 48
    assert x.start is not None and x.start.date() == (TUESDAY + timedelta(days=2)).date()


@pytest.mark.parametrize(
    "title",
    [
        "Hedge funds target euro downside amid France unrest",
        "Saudi coalition says struck Houthi missile facilities",  # not a labour strike
        "Bangladesh Bank website still offline after cyber attack",  # no logistics context
    ],
)
def test_not_supply_chain_news(title: str) -> None:
    assert not extract("c", title, None, TUESDAY).is_supply_chain_disruption


def test_resolved_and_html_titles() -> None:
    x = extract(
        "d",
        '<a href="x">Port operations resume at Chattogram after strike called off</a>',
        None,
        TUESDAY,
    )
    assert "<a" not in x.text and x.status == "resolved"


def test_syndicated_copies_collapse_and_single_source_is_capped() -> None:
    title = "Chattogram port suspends cargo handling as workers strike"
    copies = [mention(i, title, outlet="wire.example", hours=i) for i in range(3)]
    [event] = cluster(copies)
    assert len(event.mentions) == 3 and event.outlets == ["wire.example"]
    assert event.confidence <= 0.5  # one outlet, however many copies (C2 §11)
    second = mention(9, title, outlet="paper.example", hours=5)
    [event] = cluster([*copies, second])
    assert event.confidence > 0.5  # an independent outlet corroborates


def test_hazard_and_the_port_closure_it_causes_are_one_event() -> None:
    events = cluster(
        [
            mention(
                1,
                "Cyclone nears the Bay of Bengal coast, ports told to hoist signals",
                None,
                "a.example",
                0,
            ),
            mention(
                2,
                "Chattogram port suspends cargo handling ahead of the cyclone",
                None,
                "b.example",
                5,
            ),
            mention(3, "Workers strike at a Gazipur garment factory", None, "c.example", 6),
        ]
    )
    types = sorted(e.type for e in events)
    assert types == ["CYCLONE_STORM", "LABOR_STRIKE_BLOCKADE"]
    cyclone = next(e for e in events if e.type == "CYCLONE_STORM")
    assert (
        len(cyclone.mentions) == 2 and cyclone.locodes == ["BDCGP"] and cyclone.place_id == "BDCGP"
    )


def test_llm_quotes_must_exist_in_the_text() -> None:
    text = "Chattogram port suspends cargo handling ahead of Cyclone SYN-01"
    verdict, dropped = ground(
        {
            "is_supply_chain_disruption": True,
            "event_type": "CYCLONE_STORM",
            "event_type_evidence": "port suspends cargo handling",
            "locations": ["Chattogram port", "Mongla"],
            "status": "ongoing",
            "status_evidence": "operations halted for three days",  # not in the text
        },
        text,
    )
    assert verdict["event_type"] == "CYCLONE_STORM" and verdict["locations"] == ["Chattogram port"]
    assert "status" not in verdict and dropped == 2
    unsupported, _ = ground(
        {
            "is_supply_chain_disruption": True,
            "event_type": "FLOOD",
            "event_type_evidence": "",
            "locations": [],
            "status": "ongoing",
        },
        text,
    )
    assert unsupported["is_supply_chain_disruption"] is False  # no grounded type, no positive


def test_llm_no_lowers_confidence_but_keeps_the_event() -> None:
    x = extract(
        "e", "Chattogram port operations suspended as cyclone signal hoisted", None, TUESDAY
    )
    no = apply(x, {"model": "m", "verdict": {"is_supply_chain_disruption": False, "locations": []}})
    assert no.is_supply_chain_disruption and no.llm_agrees is False and no.confidence < x.confidence
    yes = apply(
        x,
        {
            "model": "m",
            "verdict": {
                "is_supply_chain_disruption": True,
                "event_type": "CYCLONE_STORM",
                "locations": [],
            },
        },
    )
    assert yes.event_type == "CYCLONE_STORM" and yes.llm_agrees is True


def test_throughput() -> None:
    """C2-AC06: ≥ 5 articles/s through triage and extraction on one core (rules: far above)."""
    import time

    t0 = time.perf_counter()
    for i in range(500):
        extract(
            str(i),
            "Transport workers call 48-hour strike on Dhaka-Chattogram highway",
            "Trucks queue at the port.",
            TUESDAY,
        )
    assert 500 / (time.perf_counter() - t0) > 50
