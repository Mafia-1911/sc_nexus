"""Raw-schema inference (genson) and per-field profiles for the source cards (03 §3 step 5)."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from genson import SchemaBuilder

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


def infer_schema(*documents: Any) -> dict[str, Any]:
    builder = SchemaBuilder(schema_uri=False)
    for doc in documents:
        builder.add_object(doc)
    schema: dict[str, Any] = builder.to_schema()
    return schema


def merge_into_schema_file(path: Path, ds_id: str, title: str, defs: dict[str, Any]) -> None:
    """One file per DS-ID; each probed endpoint is a `$defs` entry, so reruns update in place."""
    existing: dict[str, Any] = {}
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
    merged_defs = {**existing.get("$defs", {}), **defs}
    doc = {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": f"cportal:raw/{ds_id}",
        "title": f"{ds_id} · {title}: raw responses as observed by the M0 probe",
        "description": "Inferred with genson from saved probe responses. One $defs entry per call.",
        "$defs": dict(sorted(merged_defs.items())),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _step(node: Any, key: str) -> Any:
    if not key:
        return node
    if isinstance(node, dict):
        return node.get(key)
    if isinstance(node, list) and key.isdigit() and int(key) < len(node):
        return node[int(key)]
    return None


def resolve_records(doc: Any, path: str | None) -> list[Any] | None:
    """Follow a dotted path where `name[]` iterates a list, e.g. `features[].attributes`.

    Numeric parts index into lists (`1[]` is "iterate the second element"). An empty path means
    the document itself is the record list.
    """
    if path is None:
        return None
    nodes: list[Any] = [doc]
    for part in [p for p in path.split(".") if p]:
        iterate = part.endswith("[]")
        key = part[:-2] if iterate else part
        nxt: list[Any] = []
        for node in nodes:
            value = _step(node, key)
            if value is None:
                continue
            if iterate:
                if isinstance(value, list):
                    nxt.extend(value)
            else:
                nxt.append(value)
        nodes = nxt
    if len(nodes) == 1 and isinstance(nodes[0], list):
        return nodes[0]
    return nodes


@dataclass
class FieldStat:
    path: str
    types: str
    present: int
    nulls: int
    null_pct: float
    distinct: int
    example: str


def _flatten(value: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict) and value:
        for key, sub in value.items():
            yield from _flatten(sub, f"{prefix}.{key}" if prefix else str(key))
    else:
        yield prefix or "(value)", value


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _example(value: Any, limit: int = 60) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def profile_records(records: list[Any], max_fields: int = 80) -> list[FieldStat]:
    """Type mix, null share, distinct count and one example per flattened field.

    Null % counts records where the field is absent, null or an empty string.
    """
    total = len(records)
    types: dict[str, Counter[str]] = {}
    nulls: Counter[str] = Counter()
    present: Counter[str] = Counter()
    distinct: dict[str, set[str]] = {}
    examples: dict[str, Any] = {}
    order: list[str] = []
    for rec in records:
        for path, value in _flatten(rec):
            if path not in types:
                types[path] = Counter()
                distinct[path] = set()
                order.append(path)
            present[path] += 1
            if value is None or value == "":
                nulls[path] += 1
                types[path]["null"] += 1
                continue
            types[path][_type_name(value)] += 1
            if len(distinct[path]) < 1000:
                distinct[path].add(_example(value, 200))
            examples.setdefault(path, value)
    stats = []
    for path in order[:max_fields]:
        missing = total - present[path] + nulls[path]
        stats.append(
            FieldStat(
                path=path,
                types="|".join(t for t, _ in types[path].most_common() if t != "null") or "null",
                present=present[path],
                nulls=missing,
                null_pct=round(100.0 * missing / total, 1) if total else 0.0,
                distinct=len(distinct[path]),
                example=_example(examples.get(path)) if path in examples else "",
            )
        )
    return stats


def stats_to_json(stats: list[FieldStat]) -> list[dict[str, Any]]:
    return [asdict(s) for s in stats]
