"""Display names for synthetic organizations (Q-05) and the product brand (Q-07).

The database only ever stores fictional names plus a stable `name_key`. A name pack swaps the
display name at read time, so switching packs never re-seeds anything and real names are never
written next to synthetic data. Guardrail (AGENTS.md rule 3, user decision 2026-10-26): unless
a pack sets `allow_adverse: true`, a real name is replaced by the fictional one wherever the
caller shows an adverse synthetic attribute (defects, recalls, supplier failures, risk scores).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Any

import yaml

from cportal_core.paths import config_dir
from cportal_core.settings import get_settings


@dataclass(frozen=True)
class NamePack:
    pack: str
    names: dict[str, str]
    sources: dict[str, str]  # name_key → citation, for packs with real names
    real_keys: frozenset[str]
    allow_adverse: bool
    banner: str | None

    @property
    def has_real_names(self) -> bool:
        return bool(self.real_keys)


def _read(pack: str) -> dict[str, Any]:
    path = config_dir() / "name_packs" / f"{pack}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"unknown name pack {pack!r} ({path})")
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data


@cache
def load_pack(pack: str | None = None) -> NamePack:
    pack = pack or get_settings().name_pack
    data = _read(pack)
    names: dict[str, str] = {}
    sources: dict[str, str] = {}
    real: set[str] = set()
    if parent := data.get("extends"):
        base = load_pack(parent)
        names.update(base.names)
        sources.update(base.sources)
    for key, value in (data.get("names") or {}).items():
        if isinstance(value, dict):
            names[key] = str(value["name"])
            if value.get("source"):
                sources[key] = str(value["source"])
            real.add(key)
        else:
            names[key] = str(value)
    return NamePack(
        pack=pack,
        names=names,
        sources=sources,
        real_keys=frozenset(real),
        allow_adverse=bool(data.get("allow_adverse", False)),
        banner=data.get("banner"),
    )


def fictional_name(name_key: str | None, fallback: str) -> str:
    return load_pack("fictional").names.get(name_key or "", fallback)


def display_name(
    name_key: str | None, fallback: str, *, adverse: bool = False, pack: NamePack | None = None
) -> str:
    """The name to show for an organization in the active pack.

    `adverse=True` marks views that attach adverse synthetic attributes to the firm."""
    active = pack or load_pack()
    if not name_key or name_key not in active.names:
        return fallback
    if adverse and name_key in active.real_keys and not active.allow_adverse:
        return fictional_name(name_key, fallback)
    return active.names[name_key]


def brand_name() -> str:
    return get_settings().brand_name
