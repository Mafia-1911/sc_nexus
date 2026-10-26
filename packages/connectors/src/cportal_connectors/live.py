"""Live fetching (02 §8 "probe/fetch"): polite HTTP into the immutable raw zone, then the same
parsers as replay and synthetic (ADR-010).

Raw responses land verbatim (secrets masked) in `data/raw/<DS-ID>/<YYYY-MM-DD>/<ts>_<name>.<ext>`
with a `.meta.json` beside them. A source declares `live_calls()`; multi-step sources (GDELT)
override `Connector.live()`.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from cportal_core.enums import DataMode
from cportal_core.paths import raw_dir
from cportal_core.settings import Settings

from cportal_connectors.base import TokenBucket
from cportal_connectors.canonical import ParseContext, Parser
from cportal_connectors.redact import Redactor


class LiveError(RuntimeError):
    """A live call failed (HTTP status, network, or decode). Counts as one strike."""


@dataclass(frozen=True)
class LiveCall:
    name: str
    url: str
    parser: Parser
    params: Mapping[str, Any] | None = None
    headers: Mapping[str, str] | None = None
    ext: str = "json"
    timeout_s: float = 60.0


class LiveHttp:
    """What a connector's `live()` sees: polite GETs that are archived as they arrive."""

    def __init__(
        self,
        ds_id: str,
        settings: Settings,
        *,
        min_interval_s: float = 1.0,
        transport: httpx.BaseTransport | None = None,
        root: Path | None = None,
    ) -> None:
        self.ds_id = ds_id
        self.settings = settings
        self.redactor = Redactor(settings.secret_values())
        self.bucket = TokenBucket.every(min_interval_s)
        self.root = root or raw_dir(ds_id)
        self.client = httpx.Client(
            headers={"User-Agent": settings.user_agent()},
            follow_redirects=True,
            transport=transport,
        )
        self.fetched_at: datetime | None = None
        self.saved: list[Path] = []

    def secret(self, env_name: str) -> str | None:
        return self.settings.secret(env_name)

    def get(
        self,
        name: str,
        url: str,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        ext: str = "json",
        timeout_s: float = 60.0,
        archive_transform: Callable[[bytes], bytes] | None = None,
    ) -> bytes:
        """GET and archive. `archive_transform` reduces what is kept on disk (e.g. RSS to
        metadata and snippets: the news guardrail, 03 §5); error pages are kept as they are."""
        self.bucket.acquire()
        t0 = time.perf_counter()
        try:
            response = self.client.get(
                url, params=dict(params or {}), headers=dict(headers or {}), timeout=timeout_s
            )
        except httpx.HTTPError as exc:
            raise LiveError(f"{name}: {type(exc).__name__}") from exc
        self.fetched_at = datetime.now(UTC)
        body = response.content
        kept = body
        if archive_transform is not None and response.status_code < 400:
            kept = archive_transform(body)
        self._archive(name, ext, kept, response, (time.perf_counter() - t0) * 1000)
        if response.status_code >= 400:
            raise LiveError(f"{name}: HTTP {response.status_code}")
        return body

    def _archive(
        self, name: str, ext: str, body: bytes, response: httpx.Response, ms: float
    ) -> None:
        assert self.fetched_at is not None
        folder = self.root / self.fetched_at.strftime("%Y-%m-%d")
        folder.mkdir(parents=True, exist_ok=True)
        stem = f"{self.fetched_at.strftime('%Y%m%dT%H%M%SZ')}_{name}"
        path = folder / f"{stem}.{ext}"
        path.write_bytes(self.redactor.bytes(body))
        meta = {
            "url": self.redactor.url(str(response.url)),
            "status": response.status_code,
            "latency_ms": round(ms, 1),
            "bytes": len(body),
            "content_type": response.headers.get("content-type"),
            "fetched_at": self.fetched_at.isoformat(),
        }
        (folder / f"{stem}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        self.saved.append(path)

    def ctx(self) -> ParseContext:
        return ParseContext(self.ds_id, DataMode.LIVE, fetched_at=self.fetched_at)

    def close(self) -> None:
        self.client.close()
