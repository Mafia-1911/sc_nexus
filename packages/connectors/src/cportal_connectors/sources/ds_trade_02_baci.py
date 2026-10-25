"""DS-TRADE-02 · CEPII BACI: harmonised HS6 bilateral trade flows (annual bulk zips)."""

from __future__ import annotations

from cportal_connectors.base import Connector
from cportal_connectors.harness import ProbeContext
from cportal_connectors.landing import landing_and_files


class Baci(Connector):
    ds_id = "DS-TRADE-02"
    title = "CEPII BACI"

    def probe(self, ctx: ProbeContext) -> None:
        landing_and_files(
            ctx,
            "cepii_page",
            "https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37",
            r"\.zip$",
            max_files=1,
        )


CONNECTOR = Baci()
