from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from cportal_connectors.base import Connector, ProbeCall
from cportal_connectors.harness import ProbeContext, guess_ext, run_probe
from cportal_core.settings import Settings
from pydantic import SecretStr

SECRET = "s3cr3t-token-value"


class Fake(Connector):
    ds_id = "DS-TEST-01"
    title = "fake source"

    def probe(self, ctx: ProbeContext) -> None:
        ctx.http(
            ProbeCall(
                "records",
                "https://example.test/items",
                sample=True,
                records="items[]",
                params={"api_key": SECRET, "q": "x"},
            )
        )
        ctx.http(ProbeCall("missing", "https://example.test/nope", "bad_param"))


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/items":
        body = {
            "items": [{"id": 1, "name": "a", "note": None}, {"id": 2, "name": ""}],
            "echo": f"you sent {SECRET}",
        }
        return httpx.Response(200, json=body, headers={"x-ratelimit-remaining": "9"})
    return httpx.Response(404, text="not here")


def settings() -> Settings:
    return Settings(gfw_api_token=SecretStr(SECRET))


def test_probe_writes_redacted_evidence_schema_and_sample(sandbox: Path) -> None:
    summary = run_probe(
        Fake(), settings(), transport=httpx.MockTransport(handler), min_interval_s=0.001
    )

    run = (
        sandbox
        / "data/raw/_probes/DS-TEST-01"
        / (sandbox / "data/raw/_probes/DS-TEST-01/LATEST").read_text().strip()
    )
    request = json.loads((run / "records/request.json").read_text())
    body = (run / "records/response.json").read_text()
    assert SECRET not in json.dumps(request) and SECRET not in body
    assert "REDACTED" in request["url"]
    assert summary["calls"][0]["records"] == 2
    assert summary["calls"][0]["rate_limit_headers"] == {"x-ratelimit-remaining": "9"}
    assert summary["calls"][1]["status"] == 404
    assert summary["calls"][1]["body_excerpt"] == "not here"

    fields = {f["path"]: f for f in json.loads((run / "records/fields.json").read_text())}
    assert fields["name"]["null_pct"] == 50.0  # "" counts as missing
    assert fields["note"]["null_pct"] == 100.0  # null in one record, absent in the other

    schema: dict[str, Any] = json.loads(
        (sandbox / "schemas/raw/DS-TEST-01.schema.json").read_text()
    )
    assert "records" in schema["$defs"]
    assert (sandbox / "data/samples/DS-TEST-01/records.json").is_file()


def test_timeouts_are_recorded_not_raised(sandbox: Path) -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    class Slow(Connector):
        ds_id = "DS-TEST-02"
        title = "slow"

        def probe(self, ctx: ProbeContext) -> None:
            ctx.http(ProbeCall("t", "https://example.test/", "timeout", timeout_s=0.001))

    summary = run_probe(
        Slow(), settings(), transport=httpx.MockTransport(slow), min_interval_s=0.001
    )
    assert summary["calls"][0]["error"].startswith("ReadTimeout")


def test_guess_ext() -> None:
    assert guess_ext("application/json; charset=utf-8", "https://x/y") == "json"
    assert guess_ext("application/octet-stream", "https://x/file.pbf") == "pbf"
    assert guess_ext("", "https://x/") == "bin"
