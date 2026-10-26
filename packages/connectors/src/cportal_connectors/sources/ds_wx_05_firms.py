"""DS-WX-05 (proposed) · NASA FIRMS active fires (VIIRS and MODIS near-real-time hotspots).

Not in the brief's registry: the user added a FIRMS MAP_KEY at G0 in place of the LANCE flood
key. Candidate use: FIRE_EXPLOSION evidence near ports, ICDs and factory clusters for C2 and
the Nexus fusion layer. The MAP_KEY sits in the URL path; the harness masks it on disk.
"""

from __future__ import annotations

import csv
import io

from cportal_core.areas import bbox

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.decoders import csv_records
from cportal_connectors.harness import ProbeContext

ROOT = "https://firms.modaps.eosdis.nasa.gov"
# A well-formed but unregistered key, for the bad-key failure mode (32 hex characters).
FAKE_KEY = "0" * 32


class Firms(Connector):
    ds_id = "DS-WX-05"
    title = "NASA FIRMS active fires (proposed)"
    needs = ("FIRMS_MAP_KEY",)
    field_notes = {
        "viirs_noaa20_bgd_2d:latitude": FieldNote("deg", "pixel centre, WGS84"),
        "viirs_noaa20_bgd_2d:bright_ti4": FieldNote("K", "I-4 channel brightness temperature"),
        "viirs_noaa20_bgd_2d:frp": FieldNote("MW", "fire radiative power"),
        "viirs_noaa20_bgd_2d:acq_date": FieldNote("", "acquisition date, UTC"),
        "viirs_noaa20_bgd_2d:acq_time": FieldNote("HHMM", "acquisition time, UTC"),
        "viirs_noaa20_bgd_2d:confidence": FieldNote("", "VIIRS: l(ow), n(ominal), h(igh)"),
        "viirs_noaa20_bgd_2d:daynight": FieldNote("", "D or N"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        b = bbox("bangladesh")
        area = f"{b.lon_min},{b.lat_min},{b.lon_max},{b.lat_max}"
        key = ctx.secret("FIRMS_MAP_KEY")
        ctx.http(
            ProbeCall(
                "bad_key",
                f"{ROOT}/api/area/csv/{FAKE_KEY}/VIIRS_NOAA20_NRT/{area}/1",
                "bad_key",
            )
        )
        if not key:
            return
        ctx.http(
            ProbeCall(
                "mapkey_status",
                f"{ROOT}/mapserver/mapkey_status/",
                "meta",
                params={"MAP_KEY": key},
                note="transaction budget for this key",
            )
        )
        ctx.http(
            ProbeCall(
                "data_availability",
                f"{ROOT}/api/data_availability/csv/{key}/ALL",
                "meta",
                decode=csv_records,
                records="[]",
            )
        )
        main = ctx.http(
            ProbeCall(
                "viirs_noaa20_bgd_2d",
                f"{ROOT}/api/area/csv/{key}/VIIRS_NOAA20_NRT/{area}/2",
                sample=True,
                decode=csv_records,
                records="[]",
                ext="csv",
                note="last 2 days of VIIRS NOAA-20 hotspots in the Bangladesh envelope",
            )
        )
        ctx.http(
            ProbeCall(
                "bad_day_range",
                f"{ROOT}/api/area/csv/{key}/VIIRS_NOAA20_NRT/{area}/99",
                "bad_param",
            )
        )
        if main.ok:
            rows = list(csv.DictReader(io.StringIO(main.body.decode("utf-8", "replace"))))
            inside = [
                r
                for r in rows
                if b.contains(float(r.get("longitude") or 0), float(r.get("latitude") or 0))
            ]
            ctx.metric("hotspots_2d_bgd_envelope", len(inside))
            ctx.metric(
                "confidence_counts",
                {c: sum(1 for r in inside if r.get("confidence") == c) for c in ("l", "n", "h")},
            )
            ctx.metric(
                "latest_acq",
                max((f"{r['acq_date']}T{r['acq_time']}" for r in inside), default=None),
            )


CONNECTOR = Firms()
