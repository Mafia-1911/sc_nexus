"""C6 tariff monitor (ADR-021, docs/proposals/C6-tariff-monitor-plan.md). Public API: `service`.

Pure parts (`rates`, `diff`) take plain `Measure` values, so they are tested without a
database; `store` reads and writes the tariff tables; `service` answers the API.
"""

NAME = "c6_tariffs"
VERSION = "0.1.0"
ENGINE_VERSION = f"c6-rates-{VERSION}"
SOURCE_ID = "C6"
