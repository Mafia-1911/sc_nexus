"""`uv run vis-fetch`: the C5 image subsets, into `data/raw/` (never committed; C5-AC07).

- DS-VIS-01 MVTec AD (CC BY-NC-SA 4.0, NC) from the Kaggle mirror `ipythonx/mvtec-ad`, file by
  file: every test image and mask of the chosen categories plus the first `--train-good` normal
  training images (few-shot references and threshold calibration). The listing is cached.
- DS-VIS-04 StitchNet v2 (CC BY 4.0) from Roboflow: the YOLOv8 export of the 483 originals.

Files already on disk are skipped, so a re-run resumes. One request at a time, ≥ 2 s apart for
Kaggle (config/sources.yaml); two strikes per file (U-02).
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from cportal_core.paths import repo_root
from cportal_core.settings import get_settings

KAGGLE = "https://www.kaggle.com/api/v1"
MVTEC = "ipythonx/mvtec-ad"
ROBOFLOW = "https://api.roboflow.com"
STITCHNET = "fabricdefectdetection-qygi0/stitchnet-defect-detection"
RAW = repo_root() / "data" / "raw"
CATEGORIES = ["pill", "capsule", "carpet", "leather"]


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": get_settings().user_agent()}, timeout=120, follow_redirects=True
    )


def _kaggle_headers() -> dict[str, str]:
    token = get_settings().secret("KAGGLE_API_TOKEN")
    if not token:
        raise RuntimeError("no Kaggle token in .env (KAGGLE_API_TOKEN)")
    return {"Authorization": f"Bearer {token}"}


def mvtec_listing(client: httpx.Client, cache: Path) -> list[dict[str, Any]]:
    if cache.exists():
        cached: list[dict[str, Any]] = json.loads(cache.read_text())
        return cached
    files: list[dict[str, Any]] = []
    token: str | None = None
    while True:
        params: dict[str, Any] = {"pageSize": 200}
        if token:
            params["pageToken"] = token
        r = client.get(f"{KAGGLE}/datasets/list/{MVTEC}", headers=_kaggle_headers(), params=params)
        r.raise_for_status()
        doc = r.json()
        files += [{"name": f["name"], "bytes": f.get("totalBytes")} for f in doc["datasetFiles"]]
        token = doc.get("nextPageToken")
        time.sleep(2)
        if not token:
            break
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(files))
    return files


def select(files: list[dict[str, Any]], categories: list[str], train_good: int) -> list[str]:
    names = sorted(f["name"] for f in files)
    out = []
    for cat in categories:
        out += [n for n in names if n.startswith((f"{cat}/test/", f"{cat}/ground_truth/"))]
        out += [n for n in names if n.startswith(f"{cat}/train/good/")][:train_good]
    return out


def fetch_mvtec(categories: list[str], train_good: int) -> int:
    root = RAW / "DS-VIS-01" / "mvtec"
    client = _client()
    listing = mvtec_listing(client, RAW / "DS-VIS-01" / "listing.json")
    wanted = select(listing, categories, train_good)
    todo = [n for n in wanted if not (root / n).exists()]
    print(f"MVTec: {len(wanted)} files wanted, {len(todo)} to fetch", flush=True)
    for i, name in enumerate(todo):
        for attempt in range(2):
            t0 = time.monotonic()
            r = client.get(
                f"{KAGGLE}/datasets/download/{MVTEC}/{quote(name, safe='')}",
                headers=_kaggle_headers(),
            )
            body = r.content
            if r.status_code == 200 and body[:2] == b"PK":  # larger files arrive zipped
                with zipfile.ZipFile(io.BytesIO(body)) as zf:
                    members = zf.namelist()
                    body = zf.read(members[0]) if len(members) == 1 else b""
            if r.status_code == 200 and body[:4] == b"\x89PNG":
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
                break
            if attempt == 1:
                print(f"  gave up on {name}: HTTP {r.status_code}", flush=True)
            time.sleep(10)
        time.sleep(max(0.0, 2.0 - (time.monotonic() - t0)))
        if i % 100 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
    return len(todo)


def fetch_stitchnet(version: int = 2) -> Path:
    out = RAW / "DS-VIS-04" / "stitchnet" / f"v{version}"
    if (out / "data.yaml").exists():
        return out
    key = get_settings().secret("ROBOFLOW_API_KEY")
    if not key:
        raise RuntimeError("no Roboflow key in .env (ROBOFLOW_API_KEY)")
    client = _client()
    r = client.get(f"{ROBOFLOW}/{STITCHNET}/{version}/yolov8", params={"api_key": key})
    r.raise_for_status()
    link = r.json()["export"]["link"]
    archive = client.get(link)
    archive.raise_for_status()
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zf:
        for member in zf.namelist():
            target = (out / member).resolve()
            if not str(target).startswith(str(out.resolve())):  # no path traversal
                raise RuntimeError(f"unsafe path in archive: {member}")
        zf.extractall(out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vis-fetch", description=__doc__.split("\n")[0])
    parser.add_argument("what", choices=["mvtec", "stitchnet", "all"])
    parser.add_argument("--categories", nargs="*", default=CATEGORIES)
    parser.add_argument("--train-good", type=int, default=60)
    args = parser.parse_args(argv)
    if args.what in ("stitchnet", "all"):
        print(f"StitchNet: {fetch_stitchnet()}", flush=True)
    if args.what in ("mvtec", "all"):
        print(f"MVTec: fetched {fetch_mvtec(args.categories, args.train_good)} files", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
