"""Probe pattern for file and page sources: landing page, then the first matching file links."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from cportal_connectors.base import ProbeCall
from cportal_connectors.decoders import html_outline
from cportal_connectors.harness import ProbeContext


def landing_and_files(
    ctx: ProbeContext, name: str, url: str, pattern: str, max_files: int = 2
) -> list[str]:
    """Fetch a landing page, list links matching `pattern`, read the first 64 KiB of a few."""
    page = ctx.http(ProbeCall(name, url, "meta", decode=html_outline, timeout_s=60))
    links = (page.parsed or {}).get("links", []) if isinstance(page.parsed, dict) else []
    final = str(page.request.get("url") or url)
    files = sorted(
        {urljoin(final, link["href"]) for link in links if re.search(pattern, link["href"], re.I)}
    )
    ctx.metric(f"{name}_file_links", files[:25])
    for i, href in enumerate(files[:max_files]):
        result = ctx.http(
            ProbeCall(
                f"{name}_file_{i}",
                href,
                max_bytes=65_536,
                timeout_s=60,
                note="first 64 KiB: availability and size",
            )
        )
        ctx.metric(f"{name}_file_{i}_bytes", result.content_length)
    return files
