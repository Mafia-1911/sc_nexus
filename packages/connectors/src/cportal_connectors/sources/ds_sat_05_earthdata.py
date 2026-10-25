"""DS-SAT-05 (proposed) · NASA Earthdata: CMR search plus token-protected downloads.

Not in the brief's registry: the user added NASA_EARTHDATA_TOKEN at kickoff. Candidate uses are
the LANCE MODIS near-real-time flood product (MCDWD_L3_NRT) for monsoon floods, and Sentinel-1
granules at the Alaska Satellite Facility as an alternative to CDSE downloads.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from cportal_core.areas import bbox

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext

CMR = "https://cmr.earthdata.nasa.gov/search"


class Earthdata(Connector):
    ds_id = "DS-SAT-05"
    title = "NASA Earthdata (proposed)"
    needs = ("EARTHDATA_TOKEN",)

    def probe(self, ctx: ProbeContext) -> None:
        b = bbox("bangladesh")
        box = f"{b.lon_min},{b.lat_min},{b.lon_max},{b.lat_max}"
        since = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        flood = ctx.http(
            ProbeCall(
                "cmr_flood_nrt_granules",
                f"{CMR}/granules.json",
                sample=True,
                records="feed.entry[]",
                params={
                    "short_name": "MCDWD_L3_NRT",
                    "bounding_box": box,
                    "temporal": f"{since},",
                    "page_size": 20,
                },
                note="MODIS NRT global flood product tiles over Bangladesh",
            )
        )
        s1 = ctx.http(
            ProbeCall(
                "cmr_s1_granules_ctg",
                f"{CMR}/granules.json",
                sample=True,
                records="feed.entry[]",
                params={
                    "short_name": "SENTINEL-1A_SLC",
                    "bounding_box": "91.5,21.7,91.95,22.3",
                    "temporal": f"{since},",
                    "page_size": 10,
                },
            )
        )
        url = self._data_url(flood.parsed) or self._data_url(s1.parsed)
        if url:
            token = ctx.secret("EARTHDATA_TOKEN")
            ctx.http(ProbeCall("protected_download_no_token", url, "no_key", max_bytes=4096))
            if token:
                ctx.http(
                    ProbeCall(
                        "protected_download_with_token",
                        url,
                        max_bytes=65_536,
                        headers={"Authorization": f"Bearer {token}"},
                        note="first 64 KiB: does the token unlock downloads?",
                    )
                )
        for name, result in (("flood_nrt", flood), ("s1_ctg", s1)):
            entries = (
                ((result.parsed or {}).get("feed") or {}).get("entry", [])
                if isinstance(result.parsed, dict)
                else []
            )
            ctx.metric(f"{name}_granules_10d", len(entries))

    @staticmethod
    def _data_url(doc: Any) -> str | None:
        entries = ((doc or {}).get("feed") or {}).get("entry", []) if isinstance(doc, dict) else []
        for entry in entries:
            for link in entry.get("links", []):
                href = str(link.get("href", ""))
                if link.get("rel", "").endswith("/data#") and href.startswith("https"):
                    return href
        return None


CONNECTOR = Earthdata()
