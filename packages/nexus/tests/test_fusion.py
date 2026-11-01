"""Evidence fusion (08 §3, NX-R03, NX-AC03): pure rules, no database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cportal_nexus.fusion import Ev, corroborate, fuse

T = datetime(2026, 10, 25, 12, tzinfo=UTC)


def news(**kw: object) -> Ev:
    base = dict(id=uuid4(), type="CYCLONE_STORM", source_id="c2", title="Port halts cargo",
                confidence=0.665, alert_level=None, start=T, lat=22.3, lon=91.8,
                locodes=("BDCGP",), outlets=2)  # fmt: skip
    return Ev(**{**base, **kw})  # type: ignore[arg-type]


def hazard(**kw: object) -> Ev:
    base = dict(id=uuid4(), type="CYCLONE_STORM", source_id="DS-PORT-01", title="Cyclone SYN-01",
                confidence=0.9, alert_level="orange", start=T + timedelta(hours=18), lat=22.1,
                lon=91.6, locodes=("BDCGP",), gdacs="9054665")  # fmt: skip
    return Ev(**{**base, **kw})  # type: ignore[arg-type]


def test_a_nearby_hazard_corroborates_the_news_and_the_news_the_hazard() -> None:
    n, h = news(), hazard()
    sig = corroborate([n, h])
    fused_n, fused_h = fuse(n, sig[n.id]), fuse(h, sig[h.id])
    assert [s.kind for s in sig[n.id]] == ["hazard"] and [s.kind for s in sig[h.id]] == ["news"]
    assert sig[n.id][0].contribution == round(1.6 * 0.7, 3)
    assert fused_n.confidence > n.confidence + 0.15 and fused_h.confidence > h.confidence
    # NX-AC03: two kinds of evidence behind the event (its news, plus the hazard feed).
    assert {"news", *(s.kind for s in sig[n.id])} == {"news", "hazard"}


def test_far_unrelated_or_stale_hazards_do_not_count() -> None:
    n = news()
    far = hazard(lat=10.0, lon=80.0, locodes=())
    unrelated = news(type="LABOR_STRIKE_BLOCKADE")
    late = hazard(start=T + timedelta(days=10))
    sig = corroborate([n, far, late])
    assert sig[n.id] == []
    assert corroborate([unrelated, hazard()])[unrelated.id] == []


def test_one_hazard_counts_once_across_feeds() -> None:
    n = news()
    sig = corroborate([n, hazard(), hazard(source_id="DS-WX-02")])
    assert len(sig[n.id]) == 1


def test_single_low_reliability_source_stays_at_or_below_half() -> None:
    """NX-R03: one weak outlet and nothing physical: capped at 0.5."""
    weak = news(source_id="DS-NEWS-02", confidence=0.7, outlets=1)
    lonely = fuse(weak, [])
    assert lonely.confidence == 0.5 and lonely.capped
    backed = fuse(weak, corroborate([weak, hazard()])[weak.id])
    assert backed.confidence > 0.5 and not backed.capped
