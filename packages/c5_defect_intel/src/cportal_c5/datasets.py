"""The real image sets C5 evaluates on (fetched by `uv run vis-fetch` into `data/raw/`).

Per category, a fixed split: up to 8 normal **reference** images (few-shot banks), 30 held-out
normal **calibration** images (the threshold at the target FPR), and the **test** images
(normal and defective). Nothing used for references or thresholds is ever tested on.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from cportal_c5.config import RAW, load_config

STITCH_CLASSES = ["overlapped_stitch", "skipped_stitch", "stain_damage", "bobbin_thread", "normal"]


@dataclass(frozen=True)
class Item:
    path: Path
    category: str
    label: str  # "good" or the defect type
    mask: Path | None
    split: str  # ref | calib | test

    @property
    def anomalous(self) -> bool:
        return self.label != "good"


def _split_normals(normals: list[Path], refs: int, calib: int) -> list[tuple[Path, str]]:
    normals = sorted(normals)
    return [
        (p, "ref" if i < refs else "calib" if i < refs + calib else "test")
        for i, p in enumerate(normals)
    ]


def mvtec(category: str, refs: int = 8, calib: int | None = None) -> list[Item]:
    calib = calib if calib is not None else int(load_config()["vision"]["calibration_normals"])
    root = RAW / "DS-VIS-01" / "mvtec" / category
    items = [
        Item(p, category, "good", None, split)
        for p, split in _split_normals(list((root / "train" / "good").glob("*.png")), refs, calib)
        if split != "test"
    ]
    for p in sorted((root / "test").glob("*/*.png")):
        kind = p.parent.name
        mask = root / "ground_truth" / kind / f"{p.stem}_mask.png"
        items.append(Item(p, category, kind, mask if mask.exists() else None, "test"))
    return items


def stitchnet(refs: int = 8, calib: int | None = None) -> list[Item]:
    calib = calib if calib is not None else int(load_config()["vision"]["calibration_normals"])
    root = RAW / "DS-VIS-04" / "stitchnet" / "v2"
    normals: list[tuple[Path, str]] = []
    defects: list[tuple[Path, str]] = []
    for label in sorted(root.glob("*/labels/*.txt")):
        classes = {int(line.split()[0]) for line in label.read_text().splitlines() if line.strip()}
        if len(classes) != 1:
            continue  # unlabelled or mixed: not usable as ground truth
        image = next(iter((label.parent.parent / "images").glob(f"{label.stem}.*")), None)
        if image is None:
            continue
        kind = STITCH_CLASSES[classes.pop()]
        (normals if kind == "normal" else defects).append((image, kind))
    items = [
        Item(p, "stitch", "good", None, split)
        for p, split in _split_normals([p for p, _ in normals], refs, calib)
    ]
    items += [Item(p, "stitch", kind, None, "test") for p, kind in defects]
    return items


def _visa_csv() -> Path | None:
    return next(iter(sorted((RAW / "DS-VIS-02").glob("**/split_csv/1cls.csv"))), None)


def visa(obj: str = "capsules", refs: int = 8, calib: int | None = None) -> list[Item]:
    """VisA (CC BY 4.0) from its own split file: train normals → references and calibration."""
    calib = calib if calib is not None else int(load_config()["vision"]["calibration_normals"])
    csv_path = _visa_csv()
    if csv_path is None:
        return []
    root = csv_path.parent.parent
    rows = list(csv.DictReader(csv_path.open()))
    train = [root / r["image"] for r in rows if r["object"] == obj and r["split"] == "train"]
    category = f"visa_{obj}"
    items = [
        Item(p, category, "good", None, split)
        for p, split in _split_normals([p for p in train], refs, calib)
        if split != "test"
    ]
    for r in rows:
        if r["object"] != obj or r["split"] != "test":
            continue
        anomalous = r["label"] == "anomaly"
        mask = root / r["mask"] if anomalous and r.get("mask") else None
        items.append(
            Item(root / r["image"], category, "anomaly" if anomalous else "good", mask, "test")
        )
    return items


def load(category: str) -> list[Item]:
    if category == "stitch":
        return stitchnet()
    if category.startswith("visa_"):
        return visa(category.removeprefix("visa_"))
    return mvtec(category)


def available(category: str) -> bool:
    if category == "stitch":
        return (RAW / "DS-VIS-04" / "stitchnet" / "v2" / "data.yaml").exists()
    if category.startswith("visa_"):
        return _visa_csv() is not None
    root = RAW / "DS-VIS-01" / "mvtec" / category
    return (root / "test").exists() and len(list((root / "train" / "good").glob("*.png"))) >= 38
