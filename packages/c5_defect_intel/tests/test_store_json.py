"""Reports with numpy numbers and NaN must fit a JSON column."""

from __future__ import annotations

import json

import numpy as np
from cportal_c5.store import jsonable


def test_numpy_and_nan_become_plain_json() -> None:
    report = {
        "auroc": np.float32(0.97), "n": np.int64(30), "ok": np.bool_(True), "fpr": float("nan"),
        "per": [np.float64(0.1), float("inf")], "nested": {1: np.float16(2)},
    }  # fmt: skip
    out = jsonable(report)
    assert out == {"auroc": out["auroc"], "n": 30, "ok": True, "fpr": None,
                   "per": [0.1, None], "nested": {"1": 2.0}}  # fmt: skip
    assert abs(out["auroc"] - 0.97) < 1e-6
    json.dumps(out, allow_nan=False)


def test_recalibration_sets_on_one_half_and_measures_on_the_other() -> None:
    from uuid import UUID

    from cportal_c5.recalibrate import plan

    normals = [(UUID(int=i), float(i), True) for i in range(40)]  # even ids calibrate
    defects = [(UUID(int=100 + i), 50.0 + i, False) for i in range(10)]
    out = plan(normals + defects, target_fpr=0.05)
    assert out["calibration_normals"] == 20 and out["held_out_normals"] == 20
    assert out["threshold"] == 38.0  # the 95th percentile of 0, 2, …, 38 ("higher")
    assert out["held_out_fpr"] == 0.05  # only 39 exceeds 38 among the 20 values 1, 3, …, 39
    assert out["recall"] == 1.0 and out["defects"] == 10
