"""C5 without images or a database: scoring, lot risk and SPC, costed options."""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import numpy as np
from cportal_c5.gallery import overlay
from cportal_c5.impact import options
from cportal_c5.risk import Lot, RiskModel, evaluate, spc
from cportal_c5.vision import Features, FewShot, image_score, mutual_scores


def _features(rng: np.random.Generator, anomalous: bool = False) -> Features:
    """A 16 × 16 grid of unit vectors around one 'normal' direction; one odd patch if anomalous."""
    base = np.zeros(32, dtype=np.float32)
    base[0] = 1.0
    patches = base + rng.normal(0, 0.15, (256, 32)).astype(np.float32)
    if anomalous:
        patches[120] = rng.normal(0, 1, 32)
    patches /= np.linalg.norm(patches, axis=1, keepdims=True)
    return Features(patches[None], (16, 16), [(0, 0, 224, 224)], (224, 224))


def test_few_shot_and_zero_shot_rank_the_odd_patch_first() -> None:
    rng = np.random.default_rng(0)
    refs = [_features(rng) for _ in range(4)]
    normal, odd = _features(rng), _features(rng, anomalous=True)
    model = FewShot(refs)
    s_normal, s_odd = model.score(normal), model.score(odd)
    assert s_odd.score > s_normal.score
    assert s_odd.heatmap.shape == (57, 57)  # 224 / 4 + 1: the source-sized map
    lot = [_features(rng) for _ in range(10)] + [odd]
    zs = mutual_scores(lot, refs=8)
    assert max(range(len(lot)), key=lambda i: zs[i].score) == len(lot) - 1  # zero-shot finds it
    assert image_score(np.array([0.0] * 99 + [1.0], dtype=np.float32)) == 1.0


def test_overlay_is_transparent_below_the_threshold() -> None:
    heat = np.zeros((20, 20), dtype=np.float32)
    heat[4:7, 4:7] = 1.0  # a defect a few patches wide
    img = np.asarray(overlay(heat, threshold=0.5, size=(40, 40)))
    assert img.shape == (40, 40, 4) and img[0, 0, 3] == 0 and img[:, :, 3].max() > 150


def _lots(drift: bool, seed: int, n_lots: int = 30) -> list[Lot]:
    rng = random.Random(seed)
    fid = uuid4()
    start = datetime(2026, 9, 1, tzinfo=UTC)
    out = []
    for i in range(n_lots):
        rate = 0.015 * (1 + (4 * i / n_lots if drift and i > n_lots / 2 else 0))
        confirmed = sum(rng.random() < rate for _ in range(125))
        out.append(
            Lot(
                uuid4(),
                fid,
                "L1",
                "garments",
                start + timedelta(days=2 * i),
                125,
                7,
                confirmed,
                confirmed > 7,
            )
        )
    return out


def test_risk_rises_on_a_drifting_line_and_spc_alarms() -> None:
    stable, drifting = _lots(False, 1), _lots(True, 2)
    model = RiskModel(stable + drifting)
    at = drifting[-1].produced_at + timedelta(hours=1)
    p_stable = model.p_fail("x", stable[0].facility_id, "garments", at, 125, 7)
    p_drift = model.p_fail(drifting[0].line_key, drifting[0].facility_id, "garments", at, 125, 7)
    assert p_drift > 3 * p_stable
    charts = spc(stable + drifting)
    assert charts[drifting[0].line_key]["alarms"] > 0
    report = evaluate(stable + drifting, test_days=20)
    assert report["n_test"] > 0 and 0 <= report["brier"] <= 1 and "reliability" in report


def test_failed_garment_lot_gets_costed_options() -> None:
    """C5-AC06: rework and replacement always; air and buyer notice when remaking is late."""
    late = options("garments", 10_000, 2000, date(2026, 10, 25), date(2026, 11, 2), 200_000)
    kinds = [str(o["action"]) for o in late]
    assert kinds == ["rework", "replace_production", "expedite_air", "notify_customer"]
    assert all(o["cost"] >= 0 and o["benefit"] is not None for o in late)
    rework, replace = late[0], late[1]
    assert rework["benefit"] == 10_000  # done in 4 days: on time
    assert replace["benefit"] < 10_000  # remaking misses the date: the late claim comes off
    relaxed = options("garments", 10_000, 2000, date(2026, 10, 1), date(2026, 12, 1), 200_000)
    assert [str(o["action"]) for o in relaxed] == ["rework", "replace_production"]


def test_pharma_lot_is_never_decided_automatically() -> None:
    kinds = {
        str(o["action"]) for o in options("pharma", 5000, 100_000, date(2026, 10, 25), None, 5000)
    }
    assert kinds == {"reinspect", "hold_shipment"}
