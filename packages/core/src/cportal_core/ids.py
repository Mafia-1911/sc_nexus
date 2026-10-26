"""Identifiers (04 §1).

Rows get UUID primary keys. Anything with a natural key gets a *deterministic* UUIDv5 from
(source, natural key, scenario), so re-ingesting a source or re-seeding a scenario upserts the
same rows instead of duplicating them, and a synthetic world is identical across machines.
"""

from __future__ import annotations

import re
import uuid
from uuid import UUID

# Fixed namespace for every Cportal UUIDv5; never change it (it would re-key every row).
NAMESPACE = UUID("4f3c2a8e-1b7d-5e60-9a41-c0de0b5e7a11")

_LOCODE = re.compile(r"^[A-Z]{2}[A-Z2-9]{3}$")
_IMO = re.compile(r"^\d{7}$")


def new_id() -> UUID:
    return uuid.uuid4()


def stable_id(*parts: object) -> UUID:
    """Deterministic UUID from any parts; None parts are kept positional."""
    key = "\x1f".join("" if p is None else str(p) for p in parts)
    return uuid.uuid5(NAMESPACE, key)


def record_id(
    table: str, source_id: str, source_record_id: str, scenario_id: UUID | None = None
) -> UUID:
    """The primary key of a canonical row that has a natural key in its source."""
    return stable_id(table, source_id, source_record_id, scenario_id)


def entity_id(table: str, scheme: str, value: object, scenario_id: UUID | None = None) -> UUID:
    """The primary key of an entity known by a cross-source identifier, so every source that
    mentions it lands on the same row: vessels by IMO (else MMSI), ports and locations by
    UN/LOCODE. Synthetic entities stay inside their scenario."""
    return stable_id(table, scheme, value, scenario_id)


def vessel_id(
    imo: str | None, mmsi: int | str | None, scenario_id: UUID | None = None
) -> UUID | None:
    if imo and imo_check_digit_ok(imo):
        return entity_id("vessel", "imo", imo, scenario_id)
    if mmsi:
        return entity_id("vessel", "mmsi", int(mmsi), scenario_id)
    return None


def port_id(locode: str, scenario_id: UUID | None = None) -> UUID:
    return entity_id("port", "unlocode", locode, scenario_id)


def location_id(locode: str, scenario_id: UUID | None = None) -> UUID:
    return entity_id("location", "unlocode", locode, scenario_id)


def normalize_locode(raw: str | None) -> str | None:
    """'BD CGP', 'bdcgp', 'BD-CGP' → 'BDCGP'; anything else → None (PortWatch writes spaces)."""
    if not raw:
        return None
    code = re.sub(r"[\s\-]", "", raw).upper()
    return code if _LOCODE.match(code) else None


def imo_check_digit_ok(imo: str | int | None) -> bool:
    """IMO ship numbers: the 7th digit is sum(d_i * (7 - i)) mod 10 over the first six."""
    text = str(imo or "")
    if not _IMO.match(text):
        return False
    digits = [int(c) for c in text]
    return sum(d * (7 - i) for i, d in enumerate(digits[:6])) % 10 == digits[6]


def mmsi_mid(mmsi: str | int | None) -> int | None:
    """Maritime Identification Digits of a ship-station MMSI (405 = Bangladesh, 999 = synthetic)."""
    text = str(mmsi or "")
    if len(text) != 9 or not text.isdigit():
        return None
    mid = int(text[:3])
    # Ship stations use MIDs 201-775; 999 is reserved here for synthetic vessels (A-012).
    return mid if 201 <= mid <= 775 or mid == 999 else None
