"""Changes between two snapshots of one schedule scope (pure).

Two measures are "the same rule" when their natural key matches (market, product code, kind,
origin, source reference). A rule present only in the new snapshot is added, only in the old
one removed, and in both with a different content hash changed. `delta_pp` is the change in
the rate that *applies*: a terminated or removed measure applies 0 %.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from cportal_c6.rates import Measure

Key = tuple[str, str, str, str, str]


def natural_key(m: Measure) -> Key:
    return (m.market, m.code, m.kind, m.origin_code, m.measure_ref)


def _applied(m: Measure | None) -> float | None:
    if m is None or m.status == "terminated":
        return 0.0
    return m.ad_valorem_pct


@dataclass(frozen=True)
class Change:
    change: str  # added | removed | changed
    old: Measure | None
    new: Measure | None
    delta_pp: float | None
    effective_from: dt.date | None

    @property
    def key(self) -> Key:
        m = self.new or self.old
        assert m is not None
        return natural_key(m)


def diff_measures(old: list[Measure], new: list[Measure]) -> list[Change]:
    before = {natural_key(m): m for m in old}
    after = {natural_key(m): m for m in new}
    out: list[Change] = []
    for key in sorted(before.keys() | after.keys()):
        a, b = before.get(key), after.get(key)
        if a is not None and b is not None and a.content_hash == b.content_hash:
            continue
        kind = "added" if a is None else "removed" if b is None else "changed"
        pa, pb = _applied(a), _applied(b)
        delta = None if pa is None or pb is None else round(pb - pa, 4)
        out.append(Change(kind, a, b, delta, b.valid_from if b else None))
    return out
