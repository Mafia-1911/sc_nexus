"""DS-SAT-01 · Copernicus Data Space Ecosystem: Sentinel-1 GRD and Sentinel-2 L2A over Chattogram.

Catalogue search is public; downloads need a free CDSE account (not provided yet).
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from cportal_core.areas import bbox

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext

STAC = "https://stac.dataspace.copernicus.eu/v1"


class Cdse(Connector):
    ds_id = "DS-SAT-01"
    title = "Copernicus Data Space Ecosystem (STAC)"
    field_notes = {
        "s1_grd_ctg_60d:properties.datetime": FieldNote("UTC", "Acquisition time"),
        "s1_grd_ctg_60d:properties.platform": FieldNote("", "sentinel-1a / -1c"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        b = bbox("ctg_outer_anchorage")
        box = f"{b.lon_min},{b.lat_min},{b.lon_max},{b.lat_max}"
        end = datetime.now(UTC).replace(microsecond=0)
        window = f"{(end - timedelta(days=60)).isoformat()}/{end.isoformat()}".replace(
            "+00:00", "Z"
        )
        ctx.http(ProbeCall("collections", f"{STAC}/collections", "meta"))
        s1 = ctx.http(
            ProbeCall(
                "s1_grd_ctg_60d",
                f"{STAC}/search",
                sample=True,
                records="features[]",
                params={
                    "collections": "sentinel-1-grd",
                    "bbox": box,
                    "datetime": window,
                    "limit": 100,
                },
            )
        )
        s2 = ctx.http(
            ProbeCall(
                "s2_l2a_ctg_60d",
                f"{STAC}/search",
                sample=True,
                records="features[]",
                params={
                    "collections": "sentinel-2-l2a",
                    "bbox": box,
                    "datetime": window,
                    "limit": 100,
                },
            )
        )
        ctx.http(
            ProbeCall(
                "bad_collection",
                f"{STAC}/search",
                "bad_param",
                params={"collections": "no-such-collection", "bbox": box, "limit": 1},
            )
        )
        ctx.metric("s1_scenes_60d", self._scenes(s1.parsed))
        ctx.metric("s2_scenes_60d", self._scenes(s2.parsed, cloud=True))

    @staticmethod
    def _scenes(doc: Any, cloud: bool = False) -> dict[str, Any]:
        feats = doc.get("features", []) if isinstance(doc, dict) else []
        days = sorted({str(f.get("properties", {}).get("datetime"))[:10] for f in feats})
        out: dict[str, Any] = {
            "items": len(feats),
            "distinct_days": len(days),
            "platforms": dict(Counter(str(f.get("properties", {}).get("platform")) for f in feats)),
        }
        if cloud:
            covers = [f.get("properties", {}).get("eo:cloud_cover") for f in feats]
            covers = [c for c in covers if isinstance(c, int | float)]
            out["below_30pct_cloud"] = sum(c < 30 for c in covers)
        return out


CONNECTOR = Cdse()
