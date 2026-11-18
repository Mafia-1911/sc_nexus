"""DS-TRADE-08 · EU tariff preferences (manual table, `config/tariffs/eu_preferences.yaml`).

There is no free EU tariff API that answered the probe (docs/tariffs/LIVE_FEEDS.md), so who
gets which EU preference is a hand-kept, cited table; the EU MFN rates come from WITS
(DS-TRADE-04). The probe only checks that TARIC is reachable.
"""

from __future__ import annotations

from collections.abc import Iterable

from cportal_core.enums import DataMode
from cportal_core.paths import config_dir
from cportal_core.schemas.records import (
    Record,
    TariffMeasureRecord,
    TariffOriginGroupRecord,
    TariffOriginMemberRecord,
    TariffSnapshotRecord,
)

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.canonical import ParseContext
from cportal_connectors.harness import ProbeContext
from cportal_connectors.parsers.tariffs import eu_prefs_as_of, parse_eu_preferences

TABLE = "eu_preferences.yaml"


class EuPreferences(Connector):
    ds_id = "DS-TRADE-08"
    title = "EU tariff preferences (manual)"
    parsers = {TABLE: parse_eu_preferences}
    record_types = (
        TariffOriginGroupRecord,
        TariffOriginMemberRecord,
        TariffMeasureRecord,
        TariffSnapshotRecord,
    )

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(
            ProbeCall("taric_home", "https://ec.europa.eu/taxation_customs/dds2/taric/", "meta")
        )

    def replay(self, names: Iterable[str] | None = None) -> list[Record]:
        """The table lives in config, not in data/samples: it is maintained, not captured."""
        body = (config_dir() / "tariffs" / TABLE).read_bytes()
        ctx = ParseContext(self.ds_id, DataMode.REPLAY, fetched_at=eu_prefs_as_of(body))
        return parse_eu_preferences(body, ctx)


CONNECTOR = EuPreferences()
