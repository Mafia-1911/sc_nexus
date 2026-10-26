# ShipperFast (codename Cportal)

A supply-chain resilience platform proven on Bangladesh's Chattogram–Dhaka corridor for garment
and pharma shippers. The full specification is in [`docs/brief/`](docs/brief/00-INDEX.md); agents
start from [`AGENTS.md`](AGENTS.md), and progress lives in [`docs/STATUS.md`](docs/STATUS.md).

**Current milestone: M1 (Architecture), at gate G1.** The domain model, canonical parsers for
every P0 source, the synthetic world with a calibrated Chattogram port simulation, and the API
skeleton exist. The web app and worker arrive in M2.

> Synthetic data is never presented as real: every row carries `data_mode` and `is_synthetic`,
> every API response carries a `meta.mode` badge, and synthetic firms are fictional.

## Quickstart (laptop, no Docker needed)

Requires [uv](https://docs.astral.sh/uv/) (it fetches Python 3.12 itself) and GNU make.

```bash
make setup                 # uv sync: workspace + dev tools
cp .env.example .env       # then fill in the keys you have (see the comments)
make db-local              # user-level Postgres 16 + PostGIS + pgvector (installs on first run)
make seed                  # migrate, replay real samples, seed the synthetic scenarios (~30 s)
make api                   # http://127.0.0.1:8000/docs
```

With Docker instead (your user must be in the `docker` group):

```bash
make up                    # db + migrations + api on http://127.0.0.1:8000
make seed-docker           # reference replay + scenarios into the compose database
```

`make db-local` and the compose `db` both use port 5432: run one at a time
(`make db-local-stop` / `make down`).

## What is in the box

| Area | Where | Notes |
|---|---|---|
| Domain model v1 (51 tables) | `packages/core` | ORM, canonical records, loader; [ERD](docs/ERD.md); migrations in `db/alembic` |
| Sources (48 probed) | `packages/connectors` | `uv run probe`, parsers per source, `uv run ingest --replay all` |
| Synthetic world + port DES | `packages/sim` | `uv run seed`, `uv run calibrate` → [CALIBRATION.md](docs/data-sources/CALIBRATION.md) |
| API | `apps/api` | `/api/v1`, OpenAPI in [docs/api/openapi.json](docs/api/openapi.json) |
| Decisions | [docs/adr/](docs/adr/README.md), [DECISIONS.md](docs/DECISIONS.md) | ADR-001…014 |

Scenarios: `baseline` and `cyclone_supplier_delay` (the hero: a synthetic cyclone closes
Chattogram while "Fabric Mill X" floods). Select one with `?scenario=` on any API read; omit it
(`?scenario=`) for real data only.

## Probing data sources

```bash
uv run probe --list        # every DS-ID, its tier, status and whether its key is set
uv run probe DS-WX-01      # probe one source (make probe DS=DS-WX-01)
uv run probe --tier P0     # probe a whole tier, politely, one source after another
uv run probe --card DS-WX-01   # re-render the card's evidence block from the latest run
```

Each run keeps the request, the raw response and its metadata under
`data/raw/_probes/<DS-ID>/<UTC-ts>/` (gitignored), merges an inferred JSON Schema into
`schemas/raw/<DS-ID>.schema.json`, and copies small samples into `data/samples/<DS-ID>/`.
Source cards and the probe report are in [`docs/data-sources/`](docs/data-sources/).

## Checks

```bash
make check  # ruff, import boundaries, mypy, pytest (DB tests run when Postgres is up)
make calibrate  # port DES vs real marginals
make erd    # regenerate the ERD from the models
```

## Names and brand

`CPORTAL_BRAND_NAME` sets the product name. `CPORTAL_NAME_PACK=bd_demo` shows well-known
Bangladeshi company names on the hero manufacturers for the demo, with a banner; all figures stay
synthetic, and views of adverse synthetic attributes (defects, risk) keep the fictional names
([ADR-014](docs/adr/ADR-014-name-packs-and-the-brand-variable.md)).
