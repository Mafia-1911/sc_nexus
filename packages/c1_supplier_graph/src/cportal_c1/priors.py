"""C1 assumptions from `config/priors/c1.yaml`. Every value is an estimate shown as such."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from cportal_core.paths import config_dir


@dataclass(frozen=True)
class Priors:
    raw: dict[str, Any]

    @property
    def horizon_d(self) -> int:
        return int(self.raw["horizon_d"])

    @property
    def ports(self) -> dict[str, dict[str, Any]]:
        return dict(self.raw["ports"])

    @property
    def gateway(self) -> str:
        return str(self.raw["gateway"])

    @property
    def hub_reroute_d(self) -> float:
        return float(self.raw["hub_reroute_d"])

    @property
    def transit_road(self) -> float:
        return float(self.raw["transit_d"]["road"])

    @property
    def gateway_dwell(self) -> float:
        return float(self.raw["transit_d"]["gateway_dwell"])

    def sea_transit(self, country: str | None) -> float:
        t = self.raw["transit_d"]
        return float(t["sea_by_country"].get(country or "", t["sea_default"]))

    def hub_for(self, city: str | None, country: str | None) -> str | None:
        hubs = self.raw["import_hub"]
        if city in hubs["by_city"]:
            hub = hubs["by_city"][city]
            return str(hub) if hub else None
        hub = hubs["by_country"].get(country or "")
        return str(hub) if hub else None

    def export_lead(self, country: str | None) -> float:
        e = self.raw["export_lead_d"]
        return float(e["by_country"].get(country or "", e["default"]))

    @property
    def order_slack_d(self) -> float:
        return float(self.raw["order_slack_d"])

    @property
    def gateway_clearing_ratio(self) -> float:
        return float(self.raw["gateway_clearing_ratio"])

    def ttr(self, node_type: str) -> tuple[float, float]:
        table = self.raw["ttr_d"]
        p50, p90 = table.get(node_type, table["default"])
        return float(p50), float(p90)

    @property
    def tts_cap_d(self) -> float:
        return float(self.raw["tts_cap_d"])

    @property
    def ramp_d(self) -> float:
        return float(self.raw["ramp_d"])

    @property
    def surge(self) -> float:
        return float(self.raw["surge"])

    @property
    def default_cover_d(self) -> float:
        return float(self.raw["default_cover_d"])

    def hazard(self, node_type: str, cluster: str | None, overseas: bool) -> float:
        h = self.raw["hazard"]
        if node_type == "gateway":
            return float(h["gateway"])
        if overseas:
            return float(h["overseas"])
        return float(h.get(cluster or "", h["default"]))

    @property
    def risk_weights(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.raw["risk_weights"].items()}

    @property
    def risk_bands(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.raw["risk_bands"].items()}


@lru_cache(maxsize=4)
def load_priors(path: Path | None = None) -> Priors:
    file = path or config_dir() / "priors" / "c1.yaml"
    return Priors(yaml.safe_load(file.read_text()))
