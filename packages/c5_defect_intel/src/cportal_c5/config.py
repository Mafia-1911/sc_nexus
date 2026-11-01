"""C5 priors: `config/priors/c5.yaml` (categories, AQL, forecast, impact costs)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml
from cportal_core.paths import repo_root

PATH = repo_root() / "config" / "priors" / "c5.yaml"
MODELS = repo_root() / "models" / "c5"
RAW = repo_root() / "data" / "raw"
ARTIFACTS = repo_root() / "data" / "c5"  # heatmaps and gallery images (not committed)


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    cfg: dict[str, Any] = yaml.safe_load(PATH.read_text())
    return cfg
