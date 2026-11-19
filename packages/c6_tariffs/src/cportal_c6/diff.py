"""Changes between two snapshots of one schedule scope (pure).

Two measures are "the same rule" when their natural key matches (market, product code, kind,
origin, source reference). A rule present only in the new snapshot is added, only in the old
one removed, and in both with a different content hash changed. `delta_pp` is the change in
the rate that *applies*, only where the measure alone decides it:

- additive rules (MFN for every origin, column 2, additional duties): new minus old, a
  terminated or removed measure applying 0 %;
- replacing rules (preferences): a changed rate is new minus old; one added or removed has no
  delta, because what it replaces is another measure (adding a 5 % preference under a 12 % MFN
  is a cut, not +5 pp). Its direction is `direction()`;
- conditional rules (exemptions, quotas, suspensions, trade remedies): no delta.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from cportal_c6.rates import Measure

Key = tuple[str, str, str, str, str]


def natural_key(m: Measure) -> Key:
    return (m.market, m.code, m.kind, m.origin_code, m.measure_ref)


ADDITIVE = {"mfn", "column2", "additional"}


def is_preference(kind: str, origin_code: str) -> bool:
    return kind == "preferential" or (kind == "mfn" and origin_code != "*")


def direction(kind: str, origin_code: str, change: str, delta_pp: float | None) -> str | None:
    """raise | cut | exempt | None: what a change does to the duty, from its kind if no delta."""
    if delta_pp is not None and delta_pp != 0:
        return "raise" if delta_pp > 0 else "cut"
    if is_preference(kind, origin_code) and change in ("added", "removed"):
        return "cut" if change == "added" else "raise"
    if kind == "exemption" and change == "added":
        return "exempt"
    return None


def _delta(a: Measure | None, b: Measure | None) -> float | None:
    m = b or a
    assert m is not None
    if is_preference(m.kind, m.origin_code):
        if a is None or b is None or a.status == "terminated" or b.status == "terminated":
            return None
    elif m.kind not in ADDITIVE:
        return None
    pa, pb = _applied(a), _applied(b)
    return None if pa is None or pb is None else round(pb - pa, 4)


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
        out.append(Change(kind, a, b, _delta(a, b), b.valid_from if b else None))
    return out
