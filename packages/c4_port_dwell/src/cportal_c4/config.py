"""C4 priors: `config/priors/c4.yaml` (channel limits, label cleaning, split, model)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml
from cportal_core.paths import repo_root

PATH = repo_root() / "config" / "priors" / "c4.yaml"
MODELS = repo_root() / "models" / "c4"


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    cfg: dict[str, Any] = yaml.safe_load(PATH.read_text())
    return cfg
