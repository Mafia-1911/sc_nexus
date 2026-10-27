"""Calibration against openrouteservice HGV (C3-AC01, DS-GEO-03; validation only).

For a fixed set of corridor O/D pairs: ORS truck distance and duration vs our free-flow time on
the same route (edge times only: ORS models neither rush hours nor the Dhaka truck ban). One speed
multiplier is fitted (the median time ratio) and the median absolute % error is reported before
and after. ORS answers are cached, so a re-run spends no quota.
"""

from __future__ import annotations

import itertools
import json
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from cportal_core.paths import repo_root
from cportal_core.settings import get_settings
from cportal_core.timeutil import DHAKA

from cportal_c3.network import RoadNet
from cportal_c3.priors import Priors

ORS = "https://api.openrouteservice.org/v2/directions/driving-hgv"
PAIRS = [
    ("BDCGP", "BDKAM"), ("BDCGP", "gazipur"), ("BDCGP", "tongi"), ("BDCGP", "dhaka_epz"),
    ("BDCGP", "savar"), ("BDCGP", "narayanganj"), ("BDCGP", "adamjee_epz"), ("BDCGP", "BDPGN"),
    ("BDCGP", "bhaluka"), ("BDCGP", "cepz"), ("BDMGL", "BDKAM"), ("BDMGL", "gazipur"),
    ("BDMGL", "savar"), ("BDMGL", "narayanganj"), ("BDKAM", "gazipur"), ("BDKAM", "savar"),
    ("BDKAM", "dhaka_epz"), ("BDPGN", "gazipur"), ("BDPGN", "tongi"), ("cepz", "BDKAM"),
]  # fmt: skip
CACHE = repo_root() / "data" / "cache" / "c3_ors.json"


def ors(
    pairs: list[tuple[str, str]], priors: Priors, cache: Path = CACHE
) -> dict[str, dict[str, float]]:
    """ORS HGV distance (m) and duration (s) per pair, from the cache or the API (1 req/s)."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    known: dict[str, dict[str, float]] = json.loads(cache.read_text()) if cache.exists() else {}
    key = get_settings().ors_api_key
    for o, d in pairs:
        name = f"{o}>{d}"
        if name in known:
            continue
        if key is None:
            raise RuntimeError("no ORS_API_KEY / HEIGIT_KEY in .env")
        a, b = priors.places[o], priors.places[d]
        r = httpx.post(
            ORS,
            headers={
                "Authorization": key.get_secret_value(),
                "User-Agent": "ShipperFast/0.1 (Cportal)",
            },
            json={"coordinates": [[a["lon"], a["lat"]], [b["lon"], b["lat"]]]},
            timeout=30,
        )
        if r.status_code != 200:
            raise RuntimeError(f"ORS {name}: HTTP {r.status_code} {r.text[:120]}")
        summary = r.json()["routes"][0]["summary"]
        known[name] = {
            "distance_m": float(summary["distance"]),
            "duration_s": float(summary["duration"]),
        }
        cache.write_text(json.dumps(known, indent=1))
        time.sleep(1.1)
    return {f"{o}>{d}": known[f"{o}>{d}"] for o, d in pairs}


def calibrate(net: RoadNet, priors: Priors, pairs: list[tuple[str, str]] = PAIRS) -> dict[str, Any]:
    truth = ors(pairs, priors)
    rows: list[dict[str, Any]] = []
    for o, d in pairs:
        a, b = priors.places[o], priors.places[d]
        path = net.path(net.nearest(a["lat"], a["lon"]), net.nearest(b["lat"], b["lon"]))
        ours = net.traverse(path, datetime(2026, 1, 6, 2, tzinfo=DHAKA))
        free_h = sum(float(net.graph[u][v]["seconds"]) for u, v in itertools.pairwise(path)) / 3600
        t = truth[f"{o}>{d}"]
        rows.append(
            {
                "pair": f"{o}>{d}",
                "ours_h": free_h,
                "ors_h": t["duration_s"] / 3600,
                "ours_km": ours.km,
                "ors_km": t["distance_m"] / 1000,
            }
        )
    ratio = statistics.median(r["ours_h"] / r["ors_h"] for r in rows)

    def mdape(scale: float) -> float:
        return statistics.median(abs(r["ours_h"] * scale - r["ors_h"]) / r["ors_h"] for r in rows)

    km_err = statistics.median(abs(r["ours_km"] - r["ors_km"]) / r["ors_km"] for r in rows)
    current = float(priors.road["calibration"])
    return {
        "pairs": len(rows),
        "time_mdape_before": round(mdape(1.0), 3),
        "time_mdape_after": round(mdape(1 / ratio), 3),
        "distance_mdape": round(km_err, 3),
        "calibration_before": current,
        "calibration_after": round(current * ratio, 3),
        "rows": [
            {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()} for r in rows
        ],
    }
