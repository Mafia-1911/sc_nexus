"""One disruption definition for the engine and the studio; expected lateness with reroutes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from cportal_core.models import DisruptionEvent
from cportal_nexus.buffer import window
from cportal_nexus.studio import _late

NOW = datetime(2026, 10, 26, tzinfo=UTC)


def event(start_h: float, p50_h: float | None = 48, p90_h: float | None = 96) -> DisruptionEvent:
    return DisruptionEvent(
        type="CYCLONE_STORM", start_est=NOW + timedelta(hours=start_h),
        duration_p50_h=p50_h, duration_p90_h=p90_h,
    )  # fmt: skip


def test_window_starts_later_for_a_forecast_and_trims_what_has_passed() -> None:
    assert window(event(30), NOW, "p50") == (1.25, 2.0)  # starts in 1.25 d, lasts its P50
    assert window(event(30), NOW, "p90") == (1.25, 4.0)
    assert window(event(-12), NOW, "p50") == (0.0, 1.5)  # began 12 h ago: 1.5 d left
    assert window(event(-60), NOW, "p50") is None  # over before now


def test_window_falls_back_to_the_type_prior() -> None:
    assert window(event(0, None, None), NOW, "p50") == (0.0, 2.0)  # CYCLONE_STORM p50 48 h


def order(oid: str, cause: str, revenue: float, late: bool = True) -> SimpleNamespace:
    return SimpleNamespace(order_id=oid, cause=cause, revenue_usd=revenue, late=late)


def test_reroutes_save_only_gateway_blocked_orders_with_their_share() -> None:
    orders = [order("a", "gateway", 100.0), order("b", "inputs", 50.0)]
    res = SimpleNamespace(impacted_orders=[*orders, order("c", "gateway", 10.0, late=False)])
    assert _late(res, {}) == (2.0, 150.0)  # type: ignore[arg-type]
    # A reroute of "a" (60 % feasible) and of "b" (not blocked at the port: no effect).
    assert _late(res, {"a": 0.6, "b": 0.6}) == (1.4, 90.0)  # type: ignore[arg-type]
