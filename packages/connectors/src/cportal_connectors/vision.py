"""Helpers for probing image-dataset sources (DS-VIS-*) without downloading them.

M0 only proves access, size and licence: archives are read for their first 64 KiB, which gives
Content-Length and, for tar files, the first member names. Full downloads belong to M7 (C5).
"""

from __future__ import annotations

from typing import Any

from cportal_connectors.base import ProbeCall, Purpose
from cportal_connectors.harness import CallResult, ProbeContext

HEAD_BYTES = 65_536
ROBOFLOW_API = "https://api.roboflow.com"
MAGIC = {b"\xfd7zXZ\x00": "xz", b"\x1f\x8b": "gzip", b"PK\x03\x04": "zip", b"7z\xbc\xaf": "7z"}


def tar_members(head: bytes, limit: int = 12) -> list[str]:
    """Member names from the 512-byte headers that fit in the first bytes of a tar file."""
    names: list[str] = []
    offset = 0
    while offset + 512 <= len(head) and len(names) < limit:
        block = head[offset : offset + 512]
        name = block[:100].split(b"\0", 1)[0].decode("utf-8", errors="replace")
        if not name:
            break
        size_field = block[124:136].split(b"\0", 1)[0].strip() or b"0"
        try:
            size = int(size_field, 8)
        except ValueError:
            break
        names.append(name)
        offset += 512 + ((size + 511) // 512) * 512
    return names


def archive_head(
    ctx: ProbeContext, name: str, url: str, purpose: Purpose = "main", note: str = ""
) -> CallResult:
    result = ctx.http(
        ProbeCall(
            name,
            url,
            purpose,
            max_bytes=HEAD_BYTES,
            ext="bin",
            timeout_s=60,
            note=note or "first 64 KiB only",
        )
    )
    kind = next((k for magic, k in MAGIC.items() if result.body.startswith(magic)), None)
    if kind is None and result.body[257:262] == b"ustar":
        kind = "tar"
    ctx.metric(
        f"{name}_archive",
        {
            "bytes": result.content_length,
            "format": kind,
            "http": result.status,
            "first_members": tar_members(result.body) if kind == "tar" else None,
        },
    )
    return result


def roboflow_project(ctx: ProbeContext, name: str, workspace: str, project: str) -> Any:
    """Public Universe project metadata (classes, image counts, versions) via the REST API."""
    key = ctx.secret("ROBOFLOW_API_KEY")
    result = ctx.http(
        ProbeCall(
            name,
            f"{ROBOFLOW_API}/{workspace}/{project}",
            sample=True,
            params={"api_key": key} if key else None,
        )
    )
    doc = result.parsed if isinstance(result.parsed, dict) else {}
    proj = doc.get("project") or {}
    versions = doc.get("versions") or []
    ctx.metric(
        f"{name}_summary",
        {
            "http": result.status,
            "name": proj.get("name"),
            "type": proj.get("type"),
            "images": proj.get("images"),
            "classes": proj.get("classes"),
            "license": proj.get("license"),
            "versions": [v.get("id") for v in versions][:5],
            "splits_latest": (versions[0].get("splits") if versions else None),
        },
    )
    return doc
