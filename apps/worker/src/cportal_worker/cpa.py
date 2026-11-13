"""DS-PORT-10 in the worker: poll CPA's public TOS dashboard and PCS on a polite schedule.

fast every 15 min (schedule, vessels at berth, last 24 h), slow hourly (yard occupancy and
containers lying: 10–25 s each on CPA's server), daily (monthly berth occupancy and the last
week of the sailed-vessel and gate reports: berth stays for C4's wait split, A-114; truck flows,
A-115). One page at a time with gaps (cpa_tos.GAP_S); a failed poll is logged and retried on
the next tick. Off when the worker runs offline (CPORTAL_LIVE=0).
"""

from __future__ import annotations

import logging
from typing import Any

from cportal_connectors import cpa_cli

log = logging.getLogger(__name__)


def poll(which: str = "fast", database_url: str | None = None) -> dict[str, Any]:
    try:
        out = cpa_cli.poll(which, database_url)
    except Exception as exc:  # the next tick retries; never take the worker down
        log.warning("cpa poll failed", extra={"set": which, "error": str(exc)[:300]})
        return {"error": str(exc)[:300]}
    if which == "daily":
        for form in ("sailed", "gate"):  # the last week of each date-range report
            try:
                out[form] = cpa_cli.recent(form, 7, database_url)
            except Exception as exc:
                out[form] = {"error": str(exc)[:300]}
    extra = {k: out.get(k) for k in ("pages", "stored", "sailed", "gate")}
    log.info("cpa polled", extra={"set": which, **extra})
    return out
