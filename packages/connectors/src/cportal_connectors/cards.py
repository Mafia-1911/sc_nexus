"""Source cards (template: 03-data-sources.md §1), generated so they never drift from evidence.

Each card merges three inputs:
- `config/sources.yaml`: status, tier, mode, fallback, auth (what code needs);
- `docs/data-sources/cards.yaml`: narrative facts (limits, licence, coverage, quirks, mapping);
- the latest probe run: the call table, rate-limit headers, measurements and field profiles.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from cportal_core.paths import cards_dir

from cportal_connectors.base import Connector
from cportal_connectors.harness import latest_run
from cportal_connectors.registry import registry

START = "<!-- probe-evidence:start -->"
END = "<!-- probe-evidence:end -->"
HEADER_FIELDS = [
    ("status", "status"),
    ("tier", "tier"),
    ("used_by", "used by"),
    ("mode", "default mode"),
    ("fallback", "fallback (two strikes)"),
    ("auth", "auth"),
    ("signup", "sign-up"),
    ("protocol", "protocol"),
    ("pagination", "pagination"),
    ("limits_documented", "limits (documented)"),
    ("limits_observed", "limits (observed)"),
    ("licence", "licence / terms"),
    ("attribution", "attribution"),
    ("nc", "NC?"),
    ("freshness", "freshness / latency"),
    ("history", "history depth"),
    ("cadence", "update cadence"),
    ("bd_coverage", "Bangladesh coverage"),
    ("failure_modes", "failure modes observed"),
    ("quirks", "quirks"),
    ("mapping", "mapping to canonical"),
    ("synthetic_twin", "synthetic twin"),
    ("next", "next"),
]


@cache
def facts() -> dict[str, dict[str, Any]]:
    path = cards_dir() / "cards.yaml"
    data: dict[str, dict[str, Any]] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _short_url(url: str | None, limit: int = 110) -> str:
    if not url:
        return ""
    return url if len(url) <= limit else url[: limit - 1] + "…"


def _collapse(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per group: count, statuses, median latency, total bytes and records."""
    rows: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        group = call.get("group")
        if not group:
            rows.append(call)
            continue
        if group not in groups:
            groups[group] = []
            rows.append({"_group": group})
        groups[group].append(call)
    out = []
    for row in rows:
        if "_group" not in row:
            out.append(row)
            continue
        members = groups[row["_group"]]
        statuses: dict[str, int] = {}
        for m in members:
            key = str(m["status"] if m["status"] is not None else (m["error"] or "?").split(":")[0])
            statuses[key] = statuses.get(key, 0) + 1
        latencies = sorted(m["latency_ms"] for m in members if m["latency_ms"] is not None)
        records = [m["records"] for m in members if m["records"] is not None]
        out.append(
            {
                "name": f"{row['_group']} (×{len(members)})",
                "purpose": members[0]["purpose"],
                "request": members[0]["request"],
                "status": ", ".join(f"{k}×{v}" for k, v in statuses.items()),
                "latency_ms": latencies[len(latencies) // 2] if latencies else None,
                "bytes": sum(m["bytes"] for m in members),
                "records": sum(records) if records else None,
                "error": None,
                "body_excerpt": f"{len(members)} calls; first URL shown; latency is the median",
                "truncated": False,
                "note": members[0].get("note", ""),
                "rate_limit_headers": {},
            }
        )
    return out


def render_evidence(connector: Connector) -> str | None:
    run = latest_run(connector.ds_id)
    if run is None:
        return None
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    lines = [
        START,
        "",
        f"_Generated from the probe run of {summary['started_at'][:19]}Z "
        f"(`data/raw/_probes/{connector.ds_id}/{run.name}/`, local and gitignored). "
        f"Regenerate with `uv run probe --card {connector.ds_id}`._",
        "",
        "| Call | Purpose | Request | HTTP | ms | Bytes | Records | Observed |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for call in _collapse(summary["calls"]):
        status = call["status"] if call["status"] is not None else "—"
        observed = call["error"] or call["body_excerpt"] or ""
        if call.get("truncated"):
            observed = (
                f"truncated at {call['bytes']:,} B of "
                f"{call.get('content_length') or '?'}; {observed}"
            )
        if call.get("note"):
            observed = f"{call['note']} {observed}".strip()
        request = call["request"]
        lines.append(
            f"| `{call['name']}` | {call['purpose']} | `{request.get('method') or ''} "
            f"{_cell(_short_url(request.get('url')))}` | {status} | "
            f"{_cell(round(call['latency_ms']) if call['latency_ms'] is not None else '')} | "
            f"{call['bytes']:,} | {_cell(call['records'])} | {_cell(observed[:220])} |"
        )
    rate_headers = {k: v for c in summary["calls"] for k, v in c["rate_limit_headers"].items()}
    if rate_headers:
        lines += [
            "",
            "Rate-limit headers seen: "
            + ", ".join(f"`{k}: {v}`" for k, v in sorted(rate_headers.items())),
        ]
    if summary["metrics"]:
        lines += ["", "**Measured:**", ""]
        for key, value in summary["metrics"].items():
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            lines.append(f"- `{key}`: {_cell(text[:1500])}")
    if summary["notes"]:
        lines += ["", "**Notes:**", ""] + [f"- {_cell(n)}" for n in summary["notes"]]
    if summary["needs_you"]:
        lines += ["", f"**Needs you:** {', '.join(summary['needs_you'])} not set in `.env`."]
    for call in summary["calls"]:
        fields_path = run / call["name"] / "fields.json"
        if call.get("group") or not fields_path.is_file():
            continue
        fields = json.loads(fields_path.read_text(encoding="utf-8"))
        lines += [
            "",
            f"**Fields of `{call['name']}`** ({call['records']} records):",
            "",
            "| Field | Type | Unit | Null % | Distinct | Example | Meaning |",
            "|---|---|---|---|---|---|---|",
        ]
        for f in fields:
            note = connector.field_notes.get(f"{call['name']}:{f['path']}")
            lines.append(
                f"| `{_cell(f['path'])}` | {f['types']} | {_cell(note.unit if note else '')} | "
                f"{f['null_pct']} | {f['distinct']} | {_cell(f['example'])} | "
                f"{_cell(note.meaning if note else '')} |"
            )
    lines += ["", END]
    return "\n".join(lines)


def _value(ds_id: str, key: str) -> str:
    entry = {**registry().get(ds_id, {}), **facts().get(ds_id, {})}
    value = entry.get(key)
    if key == "auth" and entry.get("env"):
        value = f"{entry.get('auth')} (`{', '.join(entry['env'])}`)"
    if key == "nc" and isinstance(value, bool):
        value = "yes" if value else "no"
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    return _cell(value) if value not in (None, "") else "—"


def render_card(connector: Connector) -> str:
    ds_id = connector.ds_id
    name = registry().get(ds_id, {}).get("name", connector.title)
    schema = f"../../schemas/raw/{ds_id}.schema.json"
    has_schema = (cards_dir().parent.parent / "schemas" / "raw" / f"{ds_id}.schema.json").is_file()
    lines = [
        f"# {ds_id} · {name}",
        "",
        "<!-- Generated by `uv run probe --card` from docs/data-sources/cards.yaml, "
        "config/sources.yaml and the latest probe run. Edit those, not this file. -->",
        "",
        "| Field | Value |",
        "|---|---|",
    ]
    for key, label in HEADER_FIELDS:
        lines.append(f"| {label} | {_value(ds_id, key)} |")
    lines.append(
        f"| raw schema | {f'[{ds_id}.schema.json]({schema})' if has_schema else '—'} "
        f"(inferred with genson; field profiles below) |"
    )
    lines += ["", "## Probe evidence", "", render_evidence(connector) or "_Not probed yet._", ""]
    return "\n".join(lines)


def card_path(ds_id: str) -> Path:
    return cards_dir() / f"{ds_id}.md"


def write_card(connector: Connector) -> bool:
    path = card_path(connector.ds_id)
    text = render_card(connector)
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _first_sentence(text: str, limit: int = 140) -> str:
    """Leading sentences, at least 40 characters' worth, cut at `limit`."""
    parts = re.split(r"(?<=[.;])\s", re.sub(r"\*\*", "", text))
    cut = parts[0]
    for part in parts[1:]:
        if len(cut) >= 40:
            break
        cut = f"{cut} {part}"
    return cut if len(cut) <= limit else cut[: limit - 1] + "…"


def summary_table(ds_ids: list[str]) -> str:
    """The PROBE_REPORT summary: one row per source with the G0 columns."""
    head = (
        "| DS-ID | Tier | Status | Mode → fallback | Auth | Limits | Licence (NC) | "
        "Bangladesh coverage | Freshness | History |"
    )
    rows = [head, "|" + "---|" * 10]
    for ds_id in ds_ids:
        reg = registry().get(ds_id, {})
        fact = facts().get(ds_id, {})
        nc = " (NC)" if reg.get("nc") or fact.get("nc") is True else ""
        rows.append(
            "| "
            + " | ".join(
                _cell(x)
                for x in [
                    f"[{ds_id}]({ds_id}.md)",
                    reg.get("tier", ""),
                    reg.get("status", ""),
                    f"{reg.get('mode', '')} → {reg.get('fallback', '—')}",
                    reg.get("auth", ""),
                    _first_sentence(
                        str(fact.get("limits_documented") or fact.get("limits_observed") or "—")
                    ),
                    _first_sentence(str(fact.get("licence") or "—"), 90) + nc,
                    _first_sentence(str(fact.get("bd_coverage") or "—"), 160),
                    _first_sentence(str(fact.get("freshness") or "—"), 80),
                    _first_sentence(str(fact.get("history") or "—"), 80),
                ]
            )
            + " |"
        )
    return "\n".join(rows)
