"""DS-VIS-05 · Pharma tablet/capsule defect images on Roboflow Universe (pharma pack, C5).

MVTec `pill`/`capsule` (DS-VIS-01) and VisA `capsules` (DS-VIS-02) complete the set.
"""

from __future__ import annotations

from cportal_core.schemas.records import ImageDatasetRecord

from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext
from cportal_connectors.parsers.vision import parse_roboflow_project
from cportal_connectors.vision import ROBOFLOW_API, roboflow_project

PROJECTS = {
    "defective_tablets": ("lingeprojets", "defective_tablets-1bqis"),
    "pharmaceutical_tablet_defects": ("sabrina-adele-mesawich", "pharmaceutical-tablet-defects"),
    "defect_tablet_detection": ("briste", "defect_tablet_detection-kjn4b"),
}


class PharmaImages(Connector):
    ds_id = "DS-VIS-05"
    title = "Pharma tablet defect datasets (Roboflow Universe)"
    parsers = {
        name: parse_roboflow_project
        for name in (
            "defect_tablet_detection.json",
            "defective_tablets.json",
            "pharmaceutical_tablet_defects.json",
        )
    }
    record_types = (ImageDatasetRecord,)
    needs = ("ROBOFLOW_API_KEY",)

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(
            ProbeCall("no_key", f"{ROBOFLOW_API}/lingeprojets/defective_tablets-1bqis", "no_key")
        )
        ctx.http(
            ProbeCall(
                "bad_key",
                f"{ROBOFLOW_API}/lingeprojets/defective_tablets-1bqis",
                "bad_key",
                params={"api_key": "not-a-real-key"},
            )
        )
        if not ctx.has("ROBOFLOW_API_KEY"):
            return
        for name, (workspace, project) in PROJECTS.items():
            roboflow_project(ctx, name, workspace, project)
        ctx.http(
            ProbeCall(
                "missing_project",
                f"{ROBOFLOW_API}/lingeprojets/no-such-project",
                "bad_param",
                params={"api_key": ctx.secret("ROBOFLOW_API_KEY")},
            )
        )


CONNECTOR = PharmaImages()
