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
