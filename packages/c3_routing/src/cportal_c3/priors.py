"""C3 assumptions from `config/priors/c3.yaml` (tariffs cite sources; the rest are estimates)."""

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

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    @property
    def places(self) -> dict[str, dict[str, Any]]:
        return dict(self.raw["places"])

    @property
    def road(self) -> dict[str, Any]:
        return dict(self.raw["road"])

    def truck_ban(self) -> tuple[int, int, float, list[str]]:
        """(start hour, end hour, radius km, exempt cargo) for heavy vehicles in central Dhaka.

        Reads the user's verified DMP structure (`standard_daily.heavy_vehicles`, named corridor
        zones) or the earlier one-line form. Named corridors are modelled as a central circle of
        `radius_km` (default 8 km); route-specific exemptions are listed, not applied (A-070)."""
        ban = self.raw["road"]["truck_ban"]
        heavy = ban.get("standard_daily", {}).get("heavy_vehicles", ban)
        exempt = list(heavy.get("exempt_cargo") or [])
        return (
            int(heavy["start_h"]),
            int(heavy["end_h"]),
            float(ban.get("radius_km", heavy.get("radius_km", 8))),
            exempt,
        )

    def ban_note(self) -> str | None:
        ban = self.raw["road"]["truck_ban"]
        corridor = ban.get("standard_daily", {}).get("industrial_corridor_exemptions")
        if not corridor:
            return None
        cargo = ", ".join(corridor.get("exempt_cargo", []))
        routes = "; ".join(corridor.get("permitted_routes", []))
        return (
            f"Dhaka truck ban: {cargo} are exempt only on permitted routes ({routes}); "
            "those routes are not modelled, so the ban applies."
        )

    def speed(self, highway: str) -> float:
        table = self.raw["road"]["speed_kmh"]
        key = "link" if highway.endswith("_link") else highway
        return float(table.get(key, table["default"]))


@lru_cache(maxsize=4)
def load_priors(path: Path | None = None) -> Priors:
    return Priors(yaml.safe_load((path or config_dir() / "priors" / "c3.yaml").read_text()))
