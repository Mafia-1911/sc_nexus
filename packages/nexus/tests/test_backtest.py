"""Backtest scoring (08 §6, NX-AC06): pure functions on a toy port series."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from cportal_nexus.backtest import AlertPoint, daily, episodes, label, score

CFG = {
    "history_days": 7, "drop_ratio": 0.5, "min_median": 5, "merge_gap_days": 1,
    "match_before_days": 1, "match_after_days": 7,
    "context": [{"label": "Eid", "date": "2024-02-20", "before": 1, "after": 2}],
}  # fmt: skip
D0 = date(2024, 1, 1)


def series(drops: dict[int, int], days: int = 60, normal: int = 20) -> dict[date, int]:
    return {D0 + timedelta(days=i): drops.get(i, normal) for i in range(days)}


def alert(day: int, hour: int = 6) -> AlertPoint:
    at = datetime.combine(D0 + timedelta(days=day), datetime.min.time(), UTC) + timedelta(
        hours=hour
    )
    return AlertPoint("e", "Cyclone X", "CYCLONE_STORM", at, 80.0, "red")


def test_daily_counts_departures_per_day_including_empty_days() -> None:
    deps = [datetime(2024, 1, 1, 3, tzinfo=UTC), datetime(2024, 1, 1, 9, tzinfo=UTC)]
    assert daily(deps, D0, D0 + timedelta(days=2)) == {
        D0: 2,
        D0 + timedelta(1): 0,
        D0 + timedelta(2): 0,
    }


def test_episodes_merge_nearby_days_and_keep_the_worst_as_peak() -> None:
    eps = episodes(series({20: 8, 21: 4, 23: 9, 40: 15}), CFG)
    assert len(eps) == 1  # day 40 at 75 % is not a disruption; 20, 21 and 23 merge
    e = eps[0]
    assert (e.start, e.end, e.peak, e.peak_departures) == (
        D0 + timedelta(20),
        D0 + timedelta(23),
        D0 + timedelta(21),
        4,
    )


def test_score_reports_lead_time_precision_recall_and_misses() -> None:
    eps = episodes(series({20: 4, 50: 3}), CFG)  # two disruptions
    report = score([alert(18), alert(30)], eps, CFG)  # one warns 2 days ahead, one is false
    assert report["k04_precision"] == 0.5 and report["recall"] == 0.5
    assert report["k03_lead_time_h"]["median"] == 2 * 24 + 6  # day 18 06:00 → day 20 12:00
    assert len(report["missed"]) == 1 and len(report["false_alarms"]) == 1


def test_context_labels_explain_but_do_not_score() -> None:
    eps = episodes(series({50: 3}), CFG)
    assert label(eps[0], CFG) == ["Eid (2024-02-20)"]
    assert score([], eps, CFG)["recall"] == 0.0  # still a miss


def test_two_alerts_before_one_disruption_count_once_for_recall_and_lead_time() -> None:
    eps = episodes(series({20: 4}), CFG)
    report = score([alert(17), alert(18)], eps, CFG)  # e.g. a cyclone and its flood
    assert report["k04_precision"] == 1.0  # both alerts were followed by the disruption
    assert report["recall"] == 1.0 and report["episodes_warned"] == 1
    assert report["k03_lead_time_h"] == {"median": 78.0, "min": 78.0, "max": 78.0, "n": 1}
