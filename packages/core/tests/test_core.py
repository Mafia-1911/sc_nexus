from __future__ import annotations

from pathlib import Path

import pytest
from cportal_core import paths
from cportal_core.areas import BBox, bbox, bbox_names
from cportal_core.settings import Settings

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "AGENTS.md").write_text("x")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    for name in list(Settings.model_fields):
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setenv("CPORTAL_ROOT", str(tmp_path))
    paths.repo_root.cache_clear()
    yield tmp_path / ".env"
    paths.repo_root.cache_clear()


def test_settings_accept_aliases_and_quoted_names(env_file: Path) -> None:
    env_file.write_text('"AIS_STREAM_APIKEY"="abc123"\nUN_COMTRADE_APIKEY="def456"\n')
    s = Settings()
    assert s.secret("AISSTREAM_API_KEY") == "abc123"
    assert s.secret("COMTRADE_API_KEY") == "def456"
    assert s.secret("GFW_API_TOKEN") is None
    assert sorted(s.secret_values()) == ["abc123", "def456"]


def test_post_g0_aliases_and_brand(env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CPORTAL_BRAND_NAME", raising=False)
    env_file.write_text(
        'HEIGIT_KEY="ors1"\nNASA_FIRMS_MAPKEY="firms1"\nKAGGLE_APIKEY="KGAT_x"\n'
        "RELIEFWEB_APPNAME=cportal-app\n"
    )
    s = Settings()
    assert s.secret("ORS_API_KEY") == "ors1"
    assert s.secret("FIRMS_MAP_KEY") == "firms1"
    assert s.secret("KAGGLE_API_TOKEN") == "KGAT_x"
    assert s.secret("RELIEFWEB_APPNAME") == "cportal-app"
    assert s.brand_name == "ShipperFast"
    assert "cportal-app" in s.secret_values()  # quotas are per appname, so it is redacted too


def test_environment_wins_over_dotenv(env_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file.write_text("GFW_API_TOKEN=from-file\n")
    monkeypatch.setenv("GFW_API_TOKEN", "from-env")
    assert Settings().secret("GFW_API_TOKEN") == "from-env"


def test_user_agent_contact_is_optional() -> None:
    assert "+" not in Settings(cportal_contact="").user_agent()
    assert Settings(cportal_contact="ops@example.org").user_agent().endswith("+ops@example.org)")


def test_bbox_geometry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CPORTAL_ROOT", str(REPO))
    paths.repo_root.cache_clear()
    box = bbox("ctg_outer_anchorage")
    assert box.contains(91.79, 22.09)  # the busiest GFW anchorage cell
    assert not box.contains(90.4, 23.8)  # Dhaka
    assert box.lat_lon_corners() == [[21.70, 91.50], [22.30, 91.95]]
    assert box.overpass() == "21.7,91.5,22.3,91.95"
    assert "bangladesh" in bbox_names()
    with pytest.raises(ValueError):
        BBox(1, 1, 1, 2)
