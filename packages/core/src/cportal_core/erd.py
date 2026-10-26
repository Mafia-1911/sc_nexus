"""Generate docs/ERD.md (Mermaid) from the ORM metadata: `uv run python -m cportal_core.erd`.

One diagram per domain module, so 51 tables stay readable. Lineage columns (04 §4) are listed
once instead of on every table. The file is generated; edit the models, not the ERD.
"""

from __future__ import annotations

import sys

from sqlalchemy import Table

from cportal_core.models import LINEAGE_COLUMNS, Base
from cportal_core.paths import repo_root

DOMAINS = {
    "Reference and supply network": "cportal_core.models.reference",
    "Maritime and port": "cportal_core.models.maritime",
    "News and disruption events": "cportal_core.models.events",
    "Orders, shipments and routes": "cportal_core.models.logistics",
    "Quality": "cportal_core.models.quality",
    "Platform: scenarios, alerts, models, sources, jobs": "cportal_core.models.platform",
}


def _type(column_type: object) -> str:
    name = type(column_type).__name__.lower()
    return {"geometry": "geometry", "vector": "vector", "jsonb": "jsonb", "uuid": "uuid"}.get(
        name, name.replace("varchar", "string")
    )


def _tables_by_domain() -> dict[str, list[Table]]:
    out: dict[str, list[Table]] = {d: [] for d in DOMAINS}
    module_to_domain = {m: d for d, m in DOMAINS.items()}
    for mapper in Base.registry.mappers:
        domain = module_to_domain.get(mapper.class_.__module__)
        if domain and isinstance(mapper.local_table, Table):
            out[domain].append(mapper.local_table)
    return {d: sorted(ts, key=lambda t: t.name) for d, ts in out.items()}


def diagram(tables: list[Table]) -> list[str]:
    names = {t.name for t in tables}
    lines = ["```mermaid", "erDiagram"]
    for table in tables:
        lines.append(f"  {table.name} {{")
        for col in table.columns:
            if col.name in LINEAGE_COLUMNS:
                continue
            keys = []
            if col.primary_key:
                keys.append("PK")
            if col.foreign_keys:
                keys.append("FK")
            suffix = f" {','.join(keys)}" if keys else ""
            lines.append(f"    {_type(col.type)} {col.name}{suffix}")
        lines.append("  }")
    for table in tables:
        for fk in table.foreign_keys:
            target = fk.column.table.name
            card = "|o" if fk.parent.nullable else "||"
            if target in names:
                lines.append(f'  {target} {card}--o{{ {table.name} : "{fk.parent.name}"')
            else:
                lines.append(f'  {table.name} }}o--{card} {target} : "{fk.parent.name}"')
    lines.append("```")
    return lines


def render() -> str:
    total = len(Base.metadata.tables)
    lines = [
        "# Entity-relationship diagram (domain model v1)",
        "",
        f"_Generated from `packages/core/src/cportal_core/models/` ({total} tables) by "
        "`make erd`. Edit the models, not this file._",
        "",
        "Every domain table also carries the lineage columns (04 §4, SC-01): "
        + ", ".join(f"`{c}`" for c in LINEAGE_COLUMNS)
        + ". The database enforces `is_synthetic = (data_mode = 'synthetic')` and that "
        "synthetic rows carry a `scenario_id`. `outbox_event` and `job` are infrastructure "
        "without lineage.",
        "",
    ]
    for domain, tables in _tables_by_domain().items():
        lines += [f"## {domain}", "", *diagram(tables), ""]
    return "\n".join(lines)


def main() -> int:
    out = repo_root() / "docs" / "ERD.md"
    out.write_text(render(), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
