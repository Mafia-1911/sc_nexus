"""Source registry: `config/sources.yaml` plus one connector module per DS-ID."""

from __future__ import annotations

import importlib
import pkgutil
from functools import cache
from typing import Any

import yaml
from cportal_core.paths import config_dir

from cportal_connectors import sources
from cportal_connectors.base import Connector


@cache
def registry() -> dict[str, dict[str, Any]]:
    with (config_dir() / "sources.yaml").open(encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    entries: dict[str, dict[str, Any]] = data["sources"]
    return entries


@cache
def connectors() -> dict[str, Connector]:
    """Every module in `cportal_connectors.sources` exposes `CONNECTOR`."""
    found: dict[str, Connector] = {}
    for info in pkgutil.iter_modules(sources.__path__):
        module = importlib.import_module(f"{sources.__name__}.{info.name}")
        connector = getattr(module, "CONNECTOR", None)
        if isinstance(connector, Connector):
            if connector.ds_id in found:
                raise RuntimeError(f"two connector modules claim {connector.ds_id}")
            found[connector.ds_id] = connector
    return dict(sorted(found.items()))


def min_interval_s(ds_id: str) -> float:
    entry = registry().get(ds_id, {})
    return float(entry.get("min_interval_s", 1.0))
