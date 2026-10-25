# Supply Chain Nexus (codename Cportal)

A supply-chain resilience platform proven on Bangladesh's Chattogram–Dhaka corridor for garment
and pharma shippers. The full specification is in [`docs/brief/`](docs/brief/00-INDEX.md); agents
start from [`AGENTS.md`](AGENTS.md), and progress lives in [`docs/STATUS.md`](docs/STATUS.md).

**Current milestone: M0 (Recon).** Only the source-probing toolchain exists so far.

## Setup

Requires [uv](https://docs.astral.sh/uv/) (it fetches Python 3.12 itself).

```bash
make setup                 # uv sync: workspace + dev tools
cp .env.example .env       # then fill in the keys you have (see the comments)
```

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
make test   # pytest
make lint   # ruff
make type   # mypy
```
