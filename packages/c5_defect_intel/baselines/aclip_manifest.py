"""Write C5's own calibration/test split as JSON for the AnomalyCLIP baseline (C5-AC01).

Run in the main environment (it needs `cportal_c5`); the baseline itself runs in its own venv.
Usage: uv run python packages/c5_defect_intel/baselines/aclip_manifest.py OUT.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from cportal_c5 import datasets

CATEGORIES = ["stitch", "pill", "capsule", "carpet", "leather", "visa_capsules"]


def main() -> int:
    out: dict[str, dict[str, object]] = {}
    for cat in CATEGORIES:
        if not datasets.available(cat):
            continue
        items = datasets.load(cat)
        out[cat] = {
            "masks": cat != "stitch",
            "calib": [{"path": str(i.path), "label": i.label} for i in items if i.split == "calib"],
            "test": [
                {"path": str(i.path), "label": i.label, "mask": str(i.mask) if i.mask else None}
                for i in items
                if i.split == "test"
            ],
        }
        print(cat, len(out[cat]["calib"]), len(out[cat]["test"]))  # type: ignore[arg-type]
    Path(sys.argv[1]).write_text(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
