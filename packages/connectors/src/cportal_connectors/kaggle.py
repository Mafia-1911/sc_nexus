"""Kaggle public API (v1 REST) for dataset mirrors: search, metadata and file listings.

New-style API tokens (`KGAT_…`) go in a Bearer header. Downloads are not part of probing; the
datasets are fetched once by `make fetch-…` targets when a capability needs them.
"""

from __future__ import annotations

from typing import Any

from cportal_connectors.base import ProbeCall, Purpose
from cportal_connectors.harness import CallResult, ProbeContext

API = "https://www.kaggle.com/api/v1"


def auth(ctx: ProbeContext) -> dict[str, str]:
    token = ctx.secret("KAGGLE_API_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def search(ctx: ProbeContext, name: str, query: str, purpose: Purpose = "main") -> CallResult:
    return ctx.http(
        ProbeCall(
            name,
            f"{API}/datasets/list",
            purpose,
            params={"search": query, "sortBy": "votes", "page": 1},
            headers=auth(ctx),
            records="[]",
            sample=purpose == "main",
        )
    )


def files(ctx: ProbeContext, name: str, ref: str) -> CallResult:
    return ctx.http(
        ProbeCall(
            name,
            f"{API}/datasets/list/{ref}",
            headers=auth(ctx),
            records="datasetFiles[]",
            note=f"file listing of {ref} (first page)",
        )
    )


def summarise(datasets: Any, limit: int = 8) -> list[dict[str, Any]]:
    """The fields that decide which mirror to use: size, licence, freshness, popularity."""
    if not isinstance(datasets, list):
        return []
    keep = ("ref", "title", "totalBytes", "licenseName", "lastUpdated", "downloadCount")
    return [{k: d.get(k) for k in keep} for d in datasets[:limit] if isinstance(d, dict)]
