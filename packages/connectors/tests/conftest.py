from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from cportal_core import paths

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A throwaway repo root with the real config, so probes never write into the checkout."""
    (tmp_path / "AGENTS.md").write_text("sandbox\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'sandbox'\n")
    shutil.copytree(REPO / "config", tmp_path / "config")
    monkeypatch.setenv("CPORTAL_ROOT", str(tmp_path))
    paths.repo_root.cache_clear()
    yield tmp_path
    paths.repo_root.cache_clear()
