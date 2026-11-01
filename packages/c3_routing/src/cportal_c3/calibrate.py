"""Calibration against openrouteservice HGV (C3-AC01, DS-GEO-03; validation only).

For a fixed set of corridor O/D pairs: ORS truck distance and duration vs our free-flow time on
the same route (edge times only: ORS models neither rush hours nor the Dhaka truck ban). One speed
multiplier is fitted (the median time ratio) and the median absolute % error is reported before
and after. ORS answers are cached, so a re-run spends no quota.
"""

from __future__ import annotations

import hashlib
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
RAW = repo_root() / "data" / "cache" / "ors"
MIN_INTERVAL_S = 2.0  # config/sources.yaml DS-GEO-03


class OrsQuotaExhausted(RuntimeError):
    """HTTP 403: the key's daily quota is spent; cached answers stay usable."""


class OrsClient:
    """HeiGIT openrouteservice with the provider's rules (A-083): every answer is persisted under
    `data/cache/ors/` and reused, so nothing is fetched twice; 429 (per-minute limit) waits for
    the window (Retry-After when sent, else 60 s) and retries at most twice (U-02); 403 (daily
    quota) stops at once; requests are spaced by the registry's minimum interval."""

    def __init__(
        self,
        raw: Path = RAW,
        client: httpx.Client | None = None,
        sleep: Any = time.sleep,
        min_interval_s: float = MIN_INTERVAL_S,
    ) -> None:
        self.raw = raw
        self.client = client or httpx.Client(timeout=30)
        self.sleep = sleep
        self.min_interval_s = min_interval_s
        self.requests = 0
        self._last = 0.0

    def directions(self, coords: list[list[float]]) -> dict[str, Any]:
        body = {"coordinates": [[round(x, 6), round(y, 6)] for x, y in coords]}
        key = hashlib.sha256(json.dumps(["driving-hgv", body], sort_keys=True).encode()).hexdigest()
        path = self.raw / f"{key[:24]}.json"
        if path.exists():
            cached: dict[str, Any] = json.loads(path.read_text())
            return cached
        token = get_settings().ors_api_key
        if token is None:
            raise RuntimeError("no ORS_API_KEY / HEIGIT_KEY in .env")
        for attempt in range(3):  # the first call and two retries on 429
            wait = self.min_interval_s - (time.monotonic() - self._last)
            if wait > 0:
                self.sleep(wait)
            r = self.client.post(
                ORS,
                headers={
                    "Authorization": token.get_secret_value(),
                    "User-Agent": get_settings().user_agent(),
                },
                json=body,
            )
            self._last = time.monotonic()
            self.requests += 1
            if r.status_code == 200:
                self.raw.mkdir(parents=True, exist_ok=True)
                path.write_text(r.text)
                out: dict[str, Any] = r.json()
                return out
            if r.status_code == 403:
                raise OrsQuotaExhausted(
                    "openrouteservice daily quota reached (HTTP 403); answers so far are cached, "
                    "re-run after the daily reset"
                )
            if r.status_code == 429 and attempt < 2:
                retry_after = r.headers.get("Retry-After", "")
                self.sleep(float(retry_after) if retry_after.isdigit() else 60.0)
                continue
            raise RuntimeError(f"openrouteservice: HTTP {r.status_code} {r.text[:160]}")
        raise AssertionError("unreachable")


def ors(
    pairs: list[tuple[str, str]],
    priors: Priors,
    cache: Path = CACHE,
    client: OrsClient | None = None,
) -> dict[str, dict[str, float]]:
    """ORS HGV distance (m) and duration (s) per pair, from the cache or the API."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    known: dict[str, dict[str, float]] = json.loads(cache.read_text()) if cache.exists() else {}
    client = client or OrsClient()
    for o, d in pairs:
        name = f"{o}>{d}"
        if name in known:
            continue
        a, b = priors.places[o], priors.places[d]
        doc = client.directions([[a["lon"], a["lat"]], [b["lon"], b["lat"]]])
        summary = doc["routes"][0]["summary"]
        known[name] = {
            "distance_m": float(summary["distance"]),
            "duration_s": float(summary["duration"]),
        }
        cache.write_text(json.dumps(known, indent=1))  # persist after every answer
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
