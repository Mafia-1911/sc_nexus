"""Repository-relative locations of the data zones (02-architecture.md §8)."""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path


@cache
def repo_root() -> Path:
    """The checkout root: `CPORTAL_ROOT` if set, else the nearest parent holding AGENTS.md."""
    if env := os.environ.get("CPORTAL_ROOT"):
        return Path(env).resolve()
    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError(
        "Cannot find the Cportal repo root. Run inside the repo or set CPORTAL_ROOT."
    )


def config_dir() -> Path:
    return repo_root() / "config"


def probes_dir(ds_id: str) -> Path:
    """Immutable probe evidence: data/raw/_probes/<DS-ID>/<UTC-ts>/ (gitignored)."""
    return repo_root() / "data" / "raw" / "_probes" / ds_id


def raw_dir(ds_id: str) -> Path:
    """Raw zone for collectors and fetches: data/raw/<DS-ID>/<YYYY-MM-DD>/ (gitignored)."""
    return repo_root() / "data" / "raw" / ds_id


def samples_dir(ds_id: str) -> Path:
    """Small committed samples for replay mode and contract tests (≤ 5 MB per source)."""
    return repo_root() / "data" / "samples" / ds_id


def raw_schemas_dir() -> Path:
    return repo_root() / "schemas" / "raw"


def cards_dir() -> Path:
    return repo_root() / "docs" / "data-sources"
