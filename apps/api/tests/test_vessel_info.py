"""DS-VSL-01 lookups: cached answers, "-" means not on record, a daily cap protects the trial."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cportal_api import vessel_info


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(vessel_info, "_dir", lambda: tmp_path)
    return tmp_path


def entry(pi: str) -> dict[str, object]:
    return {
        "fetched_at": datetime.now(UTC).isoformat(),
        "data": {"imo": "1105510", "management": {"P&I": pi, "manager": "X LINE",
                 "registeredOwner": "X LINE", "ClassificationSociety": "-"}},
    }  # fmt: skip


def test_cached_answers_hide_blanks_and_contacts(cache: Path) -> None:
    (cache / "412428640.json").write_text(json.dumps(entry("-")))
    out = vessel_info.cached(412428640)
    assert out is not None and out["pi_club"] is None and out["class_society"] is None
    assert out["owner"] == "X LINE" and "managerEmail" not in out
    assert vessel_info.lookup("412428640")["imo"] == "1105510"  # served from the cache


def test_no_key_or_spent_cap_never_calls_out(cache: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class NoKey:
        def secret(self, _: str) -> None:
            return None

    monkeypatch.setattr(vessel_info, "get_settings", lambda: NoKey())
    with pytest.raises(vessel_info.LookupError_) as no_key:
        vessel_info.lookup("1")
    assert no_key.value.status == 503

    class Key:
        def secret(self, _: str) -> str:
            return "k"

    monkeypatch.setattr(vessel_info, "get_settings", lambda: Key())
    today = datetime.now(UTC).date().isoformat()
    (cache / "_ledger.json").write_text(json.dumps({today: vessel_info.DAILY_CAP}))
    with pytest.raises(vessel_info.LookupError_) as capped:
        vessel_info.lookup("2")
    assert capped.value.status == 429
