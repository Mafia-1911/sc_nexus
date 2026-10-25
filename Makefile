# Cportal / Supply Chain Nexus. M0 targets only; up/seed/e2e/demo arrive with M1-M2.
.DEFAULT_GOAL := help
UV ?= uv
DS ?=

.PHONY: help setup test lint fmt type check probe probe-p0 probe-p1 cards collect-ais ais-report synth-ais

help: ## List targets
	@grep -E '^[a-z0-9-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup: ## Install the uv workspace (Python 3.12 is fetched by uv)
	$(UV) sync

test: ## Run all tests
	$(UV) run pytest

lint: ## Ruff lint and format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt: ## Apply ruff fixes and formatting
	$(UV) run ruff check . --fix
	$(UV) run ruff format .

type: ## mypy over the packages
	$(UV) run mypy

check: lint type test ## Everything CI runs

probe: ## Probe one source: make probe DS=DS-WX-01
	@test -n "$(DS)" || (echo "usage: make probe DS=<DS-ID>"; exit 2)
	$(UV) run probe $(DS)

probe-p0: ## Probe every P0 source (skips any probed in the last hour)
	$(UV) run probe --tier P0

probe-p1: ## Probe every P1 source
	$(UV) run probe --tier P1

cards: ## Regenerate all source cards from the latest probe runs (no network)
	$(UV) run probe all --card

collect-ais: ## Long-running DS-AIS-01 collector (Ctrl-C to stop)
	$(UV) run ais-collect

ais-report: ## Coverage of collected AIS (ROOT=data/synthetic/DS-AIS-01/baseline for the twin)
	$(UV) run ais-collect --report $(if $(ROOT),--root $(ROOT),)

synth-ais: ## Synthetic Chattogram AIS for the last 7 days (scenario "baseline", seed 42)
	$(UV) run ais-synth --scenario baseline --hours 168 --seed 42
