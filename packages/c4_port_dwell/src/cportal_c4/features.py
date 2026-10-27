"""Point-in-time features (C4 §5, C4-AC07).

A prediction for a vessel arriving at `as_of` sees the port as an observer at
`t = as_of - visibility_lag_h`: only arrivals and departures strictly before `t`, and anchorage
presence for days that ended by `t`. The lag stands for the feed: 0 for live AIS or a terminal
system, 24 h for CPA's daily vessel report, ≈ 96 h for GFW alone. The leakage test truncates the
data at `t` and checks that no feature changes.

Feature groups: queue state (vessels present, their mean elapsed time, cargo share), flows
(arrivals and departures over 1–7 days, their ratio: a crude utilisation), recent completed dwell
(geometric mean over 14 days), anchorage presence (GFW 4Wings), the vessel (type group,
Bangladesh flag), its history (repeat-caller count and past dwell) and the calendar.

Laid-up and stationary vessels would swamp the queue, but their final dwell is future knowledge;
instead a vessel stops counting once it has been present `max_dwell_h` (observable at `t`), and
dwell values are capped there.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import date

import numpy as np
from cportal_core.enums import ShipTypeGroup
from numpy.typing import NDArray

from cportal_c4.config import load_config
from cportal_c4.labels import EPOCH, Calls

GROUPS = [g.value for g in ShipTypeGroup] + ["unknown"]
NAMES = [
    "n_present",
    "n_present_cargo",
    "mean_elapsed_h",
    "arrivals_24h",
    "arrivals_72h",
    "arrivals_7d",
    "departures_24h",
    "departures_7d",
    "flow_ratio_7d",
    "recent_dwell_gm_14d",
    "recent_dwell_cargo_gm_14d",
    "anchorage_presence",
    "group",
    "domestic",
    "prev_calls_365d",
    "prev_dwell_gm",
    "hours_since_prev_departure",
    "month",
    "dow",
    "hour",
]
CATEGORICAL = ["group", "month", "dow"]
LABELS = {
    "n_present": "Vessels in port",
    "n_present_cargo": "Cargo vessels in port",
    "mean_elapsed_h": "Their mean time in port (h)",
    "arrivals_24h": "Arrivals, last 24 h",
    "arrivals_72h": "Arrivals, last 3 days",
    "arrivals_7d": "Arrivals, last 7 days",
    "departures_24h": "Departures, last 24 h",
    "departures_7d": "Departures, last 7 days",
    "flow_ratio_7d": "Arrivals ÷ departures, 7 days",
    "recent_dwell_gm_14d": "Typical stay, last 14 days (h)",
    "recent_dwell_cargo_gm_14d": "Typical cargo stay, last 14 days (h)",
    "anchorage_presence": "Vessels at the outer anchorage",
    "group": "Ship type",
    "domestic": "Flag",
    "prev_calls_365d": "This vessel's calls, last year",
    "prev_dwell_gm": "This vessel's usual stay (h)",
    "hours_since_prev_departure": "Hours since its last call",
    "month": "Month",
    "dow": "Weekday",
    "hour": "Arrival hour (Dhaka)",
}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def describe(name: str, value: float) -> str:
    """A feature value as people read it."""
    if np.isnan(value):
        return "unknown"
    if name == "group":
        return GROUPS[int(value)].replace("_", " ")
    if name == "domestic":
        return "Bangladesh" if value else "foreign"
    if name == "month":
        return MONTHS[int(value) - 1]
    if name == "dow":
        return DAYS[int(value)]
    if name == "hour":
        return f"{int(value):02d}:00"
    return f"{value:,.1f}" if name == "flow_ratio_7d" else f"{value:,.0f}"


DAY, WEEK = 24.0, 168.0


def _prefix(values: NDArray[np.float64]) -> NDArray[np.float64]:
    return np.concatenate([[0.0], np.cumsum(values)])


class _Flow:
    """Arrival and departure counts, presence and mean elapsed time for one set of calls."""

    def __init__(
        self, arrival: NDArray[np.float64], departure: NDArray[np.float64], cap_h: float
    ) -> None:
        dep = np.where(np.isnan(departure), np.inf, departure)
        self.arr = np.sort(arrival)
        self.arr_cum = _prefix(self.arr)
        self.dep = np.sort(dep)
        # A vessel is present at t when arrival < t <= min(departure, arrival + cap).
        leave = np.minimum(dep, arrival + cap_h)
        by_leave = np.argsort(leave, kind="stable")
        self.leave = leave[by_leave]
        self.arr_by_leave_cum = _prefix(arrival[by_leave])
        done = ~np.isinf(dep)
        by_dep = np.argsort(dep, kind="stable")
        finished = by_dep[done[by_dep]]
        self.done_dep = dep[finished]
        dwell = np.clip(dep[finished] - arrival[finished], 0.5, cap_h)
        self.log_dwell_cum = _prefix(np.log(dwell))

    def arrivals(self, t: NDArray[np.float64], window: float) -> NDArray[np.float64]:
        hi = np.searchsorted(self.arr, t, "left")
        lo = np.searchsorted(self.arr, t - window, "left")
        return (hi - lo).astype(np.float64)

    def departures(self, t: NDArray[np.float64], window: float) -> NDArray[np.float64]:
        hi = np.searchsorted(self.dep, t, "left")
        lo = np.searchsorted(self.dep, t - window, "left")
        return (hi - lo).astype(np.float64)

    def present(self, t: NDArray[np.float64]) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Vessels arrived and not departed before `t`, and their mean elapsed hours."""
        a = np.searchsorted(self.arr, t, "left")
        d = np.searchsorted(self.leave, t, "left")
        n = (a - d).astype(np.float64)
        arr_sum = self.arr_cum[a] - self.arr_by_leave_cum[d]
        with np.errstate(invalid="ignore", divide="ignore"):
            elapsed = np.where(n > 0, t - arr_sum / np.maximum(n, 1), np.nan)
        return n, elapsed

    def recent_dwell(self, t: NDArray[np.float64], window: float) -> NDArray[np.float64]:
        hi = np.searchsorted(self.done_dep, t, "left")
        lo = np.searchsorted(self.done_dep, t - window, "left")
        n = hi - lo
        with np.errstate(invalid="ignore", divide="ignore"):
            gm = np.exp((self.log_dwell_cum[hi] - self.log_dwell_cum[lo]) / n)
        return np.where(n >= 3, gm, np.nan)


class FeatureBuilder:
    def __init__(
        self,
        calls: Calls,
        presence: dict[date, float] | None = None,
        lag_h: float = 0.0,
    ) -> None:
        self.lag_h = lag_h
        self.cap_h = cap = float(load_config()["labels"]["max_dwell_h"])
        self.all = _Flow(calls.arrival, calls.departure, cap)
        cargo = np.isin(calls.group, ["cargo", "container", "dry_bulk", "general_cargo"])
        self.cargo = _Flow(calls.arrival[cargo], calls.departure[cargo], cap)
        # Presence for day D becomes visible when D has ended.
        days = sorted(presence or {})
        self.presence_end = np.array(
            [(date.toordinal(d) - EPOCH.date().toordinal() + 1) * DAY for d in days]
        )
        self.presence_val = np.array([(presence or {})[d] for d in days], dtype=np.float64)
        # Per-vessel history: arrivals and departures sorted, with log dwell of finished calls.
        self.history: dict[int, tuple[list[float], list[float], list[float]]] = {}
        by_mmsi: dict[int, list[tuple[float, float]]] = defaultdict(list)
        for m, a, d in zip(calls.mmsi, calls.arrival, calls.departure, strict=True):
            if m > 0:
                by_mmsi[int(m)].append((float(a), float(d)))
        for m, rows in by_mmsi.items():
            arr = sorted(a for a, _ in rows)
            done = sorted(
                (d, np.log(min(max(d - a, 0.5), cap))) for a, d in rows if not np.isnan(d)
            )
            self.history[m] = (arr, [d for d, _ in done], [x for _, x in done])

    def matrix(self, calls: Calls, as_of: NDArray[np.float64] | None = None) -> NDArray[np.float64]:
        """One feature row per call, as of its arrival (or the given times)."""
        as_of = calls.arrival if as_of is None else as_of
        t = as_of - self.lag_h
        n_all, elapsed = self.all.present(t)
        n_cargo, _ = self.cargo.present(t)
        arr7 = self.all.arrivals(t, WEEK)
        dep7 = self.all.departures(t, WEEK)
        if len(self.presence_end):
            idx = np.searchsorted(self.presence_end, t, "right") - 1
            presence = np.where(idx >= 0, self.presence_val[np.maximum(idx, 0)], np.nan)
            presence = np.where(
                t - self.presence_end[np.maximum(idx, 0)] > 7 * DAY, np.nan, presence
            )
        else:
            presence = np.full(len(t), np.nan)
        prev_calls, prev_dwell, since_prev = self._history(calls.mmsi, t)
        local = as_of + 6.0  # Asia/Dhaka, UTC+6, no DST
        months = (local * 3600).astype(np.int64).astype("datetime64[s]").astype("datetime64[M]")
        month = months.astype(np.int64) % 12 + 1
        dow = (np.floor(local / DAY).astype(np.int64) + 3) % 7  # 1970-01-01 was a Thursday
        group = np.array([GROUPS.index(g) if g in GROUPS else len(GROUPS) - 1 for g in calls.group])
        cols = [
            n_all,
            n_cargo,
            elapsed,
            self.all.arrivals(t, DAY),
            self.all.arrivals(t, 3 * DAY),
            arr7,
            self.all.departures(t, DAY),
            dep7,
            arr7 / np.maximum(dep7, 1.0),
            self.all.recent_dwell(t, 14 * DAY),
            self.cargo.recent_dwell(t, 14 * DAY),
            presence,
            group.astype(np.float64),
            calls.domestic.astype(np.float64),
            prev_calls,
            prev_dwell,
            since_prev,
            month.astype(np.float64),
            dow.astype(np.float64),
            np.floor(local % DAY),
        ]
        return np.column_stack(cols).astype(np.float64)

    def _history(
        self, mmsi: NDArray[np.int64], t: NDArray[np.float64]
    ) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
        n = len(t)
        prev_calls, prev_dwell, since = np.zeros(n), np.full(n, np.nan), np.full(n, np.nan)
        for i in range(n):
            h = self.history.get(int(mmsi[i]))
            if h is None:
                continue
            arr, dep, logd = h
            ti = float(t[i])
            prev_calls[i] = bisect.bisect_left(arr, ti) - bisect.bisect_left(arr, ti - 365 * DAY)
            k = bisect.bisect_left(dep, ti)
            if k:
                prev_dwell[i] = float(np.exp(np.mean(logd[:k])))
                since[i] = ti - dep[k - 1]
        return prev_calls, prev_dwell, since


def truncate(calls: Calls, t: float) -> Calls:
    """What an observer at `t` knows: calls that arrived before `t`, departures before `t`."""
    seen = calls.take(calls.arrival < t)
    seen.departure = np.where(seen.departure < t, seen.departure, np.nan)
    return seen
