"""DS-VIS-04 · Fabric and garment defect image sets (garment pack, C5).

Access differs per dataset: Roboflow (API key), Kaggle (account), Dataset Ninja mirrors,
institutional repositories. This probe proves reachability, licence and size for each.
"""

from __future__ import annotations

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.decoders import html_outline
from cportal_connectors.harness import ProbeContext
from cportal_connectors.vision import roboflow_project

PAGES = {
    "fabric_stain_kaggle": "https://www.kaggle.com/datasets/priemshpathirana/fabric-stain-dataset",
    "fabric_stain_datasetninja": "https://datasetninja.com/fabric-stain-dataset",
    "aitex_afid_original": "https://www.aitex.es/afid/",
    "aitex_afid_datasetninja": "https://datasetninja.com/afid",
    "gil_arroyo_2025_riubu": "https://riubu.ubu.es/handle/10259/10545",
    "carrilho_2024_paper": "https://www.mdpi.com/2076-3417/14/12/5298",
    "stitchingnet_mendeley": "https://data.mendeley.com/datasets/6tdthsjgfc/1",
    "fabric_defects_mendeley": "https://data.mendeley.com/datasets/663j22s43c/3",
}


class FabricDatasets(Connector):
    ds_id = "DS-VIS-04"
    title = "Fabric and garment defect datasets"
    needs = ("ROBOFLOW_API_KEY",)

    def probe(self, ctx: ProbeContext) -> None:
        statuses = {}
        for name, url in PAGES.items():
            result = ctx.http(
                ProbeCall(
                    name,
                    url,
                    "meta",
                    decode=html_outline,
                    note="landing page: availability and licence text",
                )
            )
            title = result.parsed.get("title") if isinstance(result.parsed, dict) else None
            statuses[name] = {"http": result.status, "title": (title or "")[:90]}
        ctx.metric("landing_pages", statuses)
        roboflow_project(
            ctx, "stitchnet_roboflow", "fabricdefectdetection-qygi0", "stitchnet-defect-detection"
        )


CONNECTOR = FabricDatasets()
