"""Probe harness (03-data-sources.md §3): run a connector's probe and keep the evidence.

Layout of one run:

    data/raw/_probes/<DS-ID>/<UTC-ts>/<call>/request.json   method, URL, params, headers (redacted)
                                            response.<ext>  body, verbatim apart from redaction
                                            meta.json       status, headers, latency, bytes, ...
                                            fields.json     per-field profile, when records exist
    data/raw/_probes/<DS-ID>/<UTC-ts>/summary.json          every call plus metrics and notes
    schemas/raw/<DS-ID>.schema.json                          inferred schema, one $defs per call
    data/samples/<DS-ID>/<call>.<ext>                        committed samples (≤ 5 MB per source)
"""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from cportal_core.paths import probes_dir, raw_schemas_dir, samples_dir
from cportal_core.settings import Settings

from cportal_connectors import __version__
from cportal_connectors.base import FAILURE_PURPOSES, Connector, ProbeCall, Purpose, TokenBucket
from cportal_connectors.decoders import text_of
from cportal_connectors.redact import Redactor
from cportal_connectors.schema import (
    infer_schema,
    merge_into_schema_file,
    profile_records,
    resolve_records,
    stats_to_json,
)

SAMPLE_BUDGET_BYTES = 5 * 1024 * 1024
TS_FORMAT = "%Y%m%dT%H%M%SZ"
_RATE_HEADER = re.compile(r"(?i)(rate-?limit|retry-after|quota|x-ratelimit|limit-remaining)")
_EXT_BY_TYPE = {
    "application/json": "json",
    "application/geo+json": "json",
    "application/vnd.geo+json": "json",
    "text/json": "json",
    "application/xml": "xml",
    "text/xml": "xml",
    "application/rss+xml": "xml",
    "application/atom+xml": "xml",
    "text/csv": "csv",
    "text/html": "html",
    "text/plain": "txt",
    "application/zip": "zip",
    "application/x-zip-compressed": "zip",
    "application/gzip": "gz",
    "application/x-gzip": "gz",
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}


def guess_ext(content_type: str, url: str) -> str:
    ctype = content_type.split(";")[0].strip().lower()
    if ctype in _EXT_BY_TYPE:
        return _EXT_BY_TYPE[ctype]
    suffix = Path(httpx.URL(url).path).suffix.lstrip(".").lower()
    return suffix if suffix and len(suffix) <= 5 else "bin"


@dataclass
class CallResult:
    name: str
    purpose: Purpose
    request: dict[str, Any]
    status: int | None = None
    ok: bool = False
    error: str | None = None
    latency_ms: float | None = None
    ttfb_ms: float | None = None
    size: int = 0
    content_type: str = ""
    content_length: int | None = None
    truncated: bool = False
    records: int | None = None
    rate_limit_headers: dict[str, str] = field(default_factory=dict)
    body_excerpt: str | None = None
    note: str = ""
    sample: str | None = None
    group: str | None = None
    # In memory only: the decoded body, for connectors that compute metrics from it.
    body: bytes = field(default=b"", repr=False)
    parsed: Any = field(default=None, repr=False)

    def summary(self) -> dict[str, Any]:
        keys = [
            "name",
            "purpose",
            "status",
            "ok",
            "error",
            "latency_ms",
            "ttfb_ms",
            "content_type",
            "content_length",
            "truncated",
            "records",
            "rate_limit_headers",
            "body_excerpt",
            "note",
            "sample",
            "group",
        ]
        out = {k: getattr(self, k) for k in keys}
        out["bytes"] = self.size
        out["request"] = {k: self.request.get(k) for k in ("method", "url")}
        return out


class ProbeContext:
    """What a connector's `probe()` sees: credentials, polite HTTP and the recorder."""

    def __init__(
        self,
        connector: Connector,
        settings: Settings,
        *,
        min_interval_s: float = 1.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.connector = connector
        self.ds_id = connector.ds_id
        self.settings = settings
        self.started = datetime.now(UTC)
        self.run_dir = probes_dir(self.ds_id) / self.started.strftime(TS_FORMAT)
        self.redactor = Redactor(settings.secret_values())
        self.bucket = TokenBucket.every(min_interval_s)
        self.client = httpx.Client(
            headers={"User-Agent": settings.user_agent()},
            follow_redirects=True,
            transport=transport,
        )
        self.results: list[CallResult] = []
        self.metrics: dict[str, Any] = {}
        self.notes: list[str] = []
        self.schema_defs: dict[str, Any] = {}
        self.missing = [env for env in connector.needs if not settings.secret(env)]

    # -- helpers for connectors -------------------------------------------------------------
    def has(self, env_name: str) -> bool:
        return self.settings.secret(env_name) is not None

    def secret(self, env_name: str) -> str | None:
        return self.settings.secret(env_name)

    def metric(self, key: str, value: Any) -> None:
        self.metrics[key] = value

    def note(self, text: str) -> None:
        self.notes.append(text)

    # -- HTTP --------------------------------------------------------------------------------
    def http(self, call: ProbeCall) -> CallResult:
        self.bucket.acquire()
        request = self.client.build_request(
            call.method,
            call.url,
            params=dict(call.params) if call.params else None,
            headers=dict(call.headers) if call.headers else None,
            json=call.json_body,
            content=call.data,
            timeout=call.timeout_s,
        )
        data = call.data.decode() if isinstance(call.data, bytes) else call.data
        record = {
            "method": call.method,
            "url": self.redactor.url(str(request.url)),
            "params": self.redactor.mapping(call.params),
            "headers": self.redactor.mapping(dict(request.headers)),
            "json": self.redactor.value(call.json_body),
            "data": self.redactor.text(data) if data else None,
            "timeout_s": call.timeout_s,
            "max_bytes": call.max_bytes,
            "purpose": call.purpose,
            "note": call.note,
        }
        result = CallResult(
            name=call.name, purpose=call.purpose, request=record, note=call.note, group=call.group
        )
        meta: dict[str, Any] = {}
        body = b""
        start = time.perf_counter()
        try:
            try:
                response = self.client.send(request, stream=True)
            except httpx.RemoteProtocolError:
                # The server closed a kept-alive connection (seen after GDELT 429s): retry once.
                result.note = (result.note + " [retried on a fresh connection]").strip()
                start = time.perf_counter()
                response = self.client.send(request, stream=True)
            result.ttfb_ms = round((time.perf_counter() - start) * 1000, 1)
            try:
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if call.max_bytes is not None and size >= call.max_bytes:
                        result.truncated = True
                        break
                body = b"".join(chunks)
                if call.max_bytes is not None:
                    body = body[: call.max_bytes]
            finally:
                response.close()
            result.latency_ms = round((time.perf_counter() - start) * 1000, 1)
            result.status = response.status_code
            result.ok = response.is_success
            result.content_type = response.headers.get("content-type", "")
            length = response.headers.get("content-length")
            result.content_length = int(length) if length and length.isdigit() else None
            result.rate_limit_headers = {
                k: v for k, v in response.headers.items() if _RATE_HEADER.search(k)
            }
            meta = {
                "status": response.status_code,
                "reason": response.reason_phrase,
                "http_version": response.http_version,
                "final_url": self.redactor.url(str(response.url)),
                "redirects": [self.redactor.url(str(r.url)) for r in response.history],
                "headers": {
                    k: ("<present>" if k.lower() == "set-cookie" else self.redactor.text(v))
                    for k, v in response.headers.items()
                },
                "encoding": response.encoding,
            }
        except httpx.HTTPError as exc:
            result.latency_ms = round((time.perf_counter() - start) * 1000, 1)
            result.error = f"{type(exc).__name__}: {exc}"
        ext = call.ext or guess_ext(result.content_type, call.url)
        self._finish(result, call, body, ext, meta)
        return result

    # -- non-HTTP evidence (WebSocket sessions, offline packages, derived files) --------------
    def record_local(
        self,
        name: str,
        *,
        request: dict[str, Any],
        body: bytes,
        ext: str,
        purpose: Purpose = "main",
        ok: bool = True,
        error: str | None = None,
        status: int | None = None,
        latency_ms: float | None = None,
        content_type: str = "",
        records: str | None = None,
        decode: Any = None,
        sample: bool = False,
        note: str = "",
        meta: dict[str, Any] | None = None,
        group: str | None = None,
    ) -> CallResult:
        call = ProbeCall(
            name=name,
            url=str(request.get("url", "")),
            purpose=purpose,
            records=records,
            decode=decode,
            sample=sample,
            note=note,
            ext=ext,
            group=group,
        )
        result = CallResult(
            name=name,
            purpose=purpose,
            request=self.redactor.value(request),
            status=status,
            ok=ok,
            error=error,
            latency_ms=latency_ms,
            content_type=content_type,
            note=note,
            group=group,
        )
        self._finish(result, call, body, ext, meta or {})
        return result

    # -- recording -----------------------------------------------------------------------------
    def _finish(
        self, result: CallResult, call: ProbeCall, body: bytes, ext: str, meta: dict[str, Any]
    ) -> None:
        body = self.redactor.bytes(body)
        result.body = body
        result.size = len(body)
        call_dir = self.run_dir / call.name
        call_dir.mkdir(parents=True, exist_ok=True)
        _write_json(call_dir / "request.json", result.request)
        if body:
            (call_dir / f"response.{ext}").write_bytes(body)
        if call.purpose in FAILURE_PURPOSES or not result.ok:
            excerpt = text_of(body[:600]) if body else ""
            result.body_excerpt = " ".join(excerpt.split())[:400] or None
        if result.ok and body:
            result.parsed = self._parse(call, body, ext, result)
            if result.parsed is not None and call.purpose == "main":
                self.schema_defs[call.name] = infer_schema(result.parsed)
                records = resolve_records(result.parsed, call.records)
                if records is not None:
                    result.records = len(records)
                    if records:
                        _write_json(
                            call_dir / "fields.json", stats_to_json(profile_records(records))
                        )
        if call.sample and result.ok and body:
            result.sample = self._save_sample(call, body, ext, result)
        _write_json(call_dir / "meta.json", {**meta, **result.summary()})
        self.results.append(result)
        status = result.status if result.status is not None else (result.error or "-")
        print(
            f"  {self.ds_id} {call.name:<28} {call.purpose:<10} {status!s:<6} "
            f"{result.size:>10,d} B  {result.latency_ms or 0:>8.0f} ms"
            + (f"  records={result.records}" if result.records is not None else ""),
            flush=True,
        )

    def _parse(self, call: ProbeCall, body: bytes, ext: str, result: CallResult) -> Any:
        try:
            if call.decode is not None:
                return call.decode(body)
            if ext == "json" or body[:1] in (b"{", b"["):
                return json.loads(body)
        except Exception as exc:  # a parse failure is evidence, not a crash
            result.note = (result.note + f" [parse failed: {type(exc).__name__}: {exc}]").strip()
        return None

    def _save_sample(
        self, call: ProbeCall, body: bytes, ext: str, result: CallResult
    ) -> str | None:
        target_dir = samples_dir(self.ds_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        data = call.sample_transform(body) if call.sample_transform else body
        others = sum(
            p.stat().st_size
            for p in target_dir.iterdir()
            if p.is_file() and not p.name.startswith(f"{call.name}.")
        )
        if others + len(data) > SAMPLE_BUDGET_BYTES:
            self.note(f"sample {call.name} skipped: would exceed the 5 MB budget")
            return None
        path = target_dir / f"{call.name}.{call.sample_ext or ext}"
        path.write_bytes(data)
        _write_json(
            target_dir / f"{call.name}.request.json",
            {
                **result.request,
                "captured_at": self.started.isoformat(),
                "status": result.status,
                "content_type": result.content_type,
                "transformed": call.sample_transform is not None,
            },
        )
        return str(path.relative_to(target_dir.parents[2]))

    def close(self) -> dict[str, Any]:
        self.client.close()
        summary = {
            "ds_id": self.ds_id,
            "title": self.connector.title,
            "harness_version": __version__,
            "user_agent": self.settings.user_agent(),
            "started_at": self.started.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "needs_you": self.missing,
            "calls": [r.summary() for r in self.results],
            "metrics": self.metrics,
            "notes": self.notes,
        }
        self.run_dir.mkdir(parents=True, exist_ok=True)
        _write_json(self.run_dir / "summary.json", summary)
        (self.run_dir.parent / "LATEST").write_text(self.run_dir.name + "\n", encoding="utf-8")
        if self.schema_defs:
            merge_into_schema_file(
                raw_schemas_dir() / f"{self.ds_id}.schema.json",
                self.ds_id,
                self.connector.title,
                self.schema_defs,
            )
        return summary


def latest_run(ds_id: str) -> Path | None:
    pointer = probes_dir(ds_id) / "LATEST"
    if not pointer.is_file():
        return None
    run = probes_dir(ds_id) / pointer.read_text(encoding="utf-8").strip()
    return run if run.is_dir() else None


def recently_probed(ds_id: str, within: timedelta) -> bool:
    run = latest_run(ds_id)
    if run is None:
        return False
    started = datetime.strptime(run.name, TS_FORMAT).replace(tzinfo=UTC)
    return datetime.now(UTC) - started < within


def run_probe(
    connector: Connector,
    settings: Settings,
    *,
    min_interval_s: float = 1.0,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    ctx = ProbeContext(connector, settings, min_interval_s=min_interval_s, transport=transport)
    try:
        connector.probe(ctx)
    except Exception as exc:  # keep the evidence gathered so far
        ctx.note(f"probe aborted: {type(exc).__name__}: {exc}")
        raise
    finally:
        summary = ctx.close()
    return summary


def clear_samples(ds_id: str) -> None:
    """Remove a source's committed samples before a full re-probe replaces them."""
    target = samples_dir(ds_id)
    if target.is_dir():
        shutil.rmtree(target)


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
