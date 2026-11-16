"""A-120: with API_TOKEN set, every route but /health needs the bearer token."""

from __future__ import annotations

import pytest
from cportal_api.main import create_app
from fastapi.testclient import TestClient


def test_api_token_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_TOKEN", "s3cret-token")
    c = TestClient(create_app())
    assert c.get("/health").status_code == 200
    assert c.get("/api/v1/meta").status_code == 401
    bad = c.get("/api/v1/meta", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401 and bad.json()["title"] == "Unauthorized"
    ok = c.get("/api/v1/meta", headers={"Authorization": "Bearer s3cret-token"})
    assert ok.status_code == 200
