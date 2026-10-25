"""`uv run probe <DS-ID> ...`: run source probes and regenerate the source cards."""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta

from cportal_core.settings import get_settings

from cportal_connectors.cards import card_path, summary_table, write_card
from cportal_connectors.harness import clear_samples, latest_run, recently_probed, run_probe
from cportal_connectors.registry import connectors, min_interval_s, registry

REPROBE_GUARD = timedelta(hours=1)


def _list() -> None:
    settings = get_settings()
    reg = registry()
    print(f"{'DS-ID':<14} {'tier':<4} {'status':<20} {'mode':<9} {'keys':<34} last probe")
    for ds_id, connector in connectors().items():
        entry = reg.get(ds_id, {})
        needs = [f"{env}{'' if settings.secret(env) else ' (missing)'}" for env in connector.needs]
        run = latest_run(ds_id)
        print(
            f"{ds_id:<14} {entry.get('tier', '?'):<4} {entry.get('status', '?'):<20} "
            f"{entry.get('mode', '?'):<9} {', '.join(needs) or '-':<34} "
            f"{run.name if run else '-'}"
        )
    unregistered = sorted(set(reg) - set(connectors()))
    if unregistered:
        print(f"\nIn sources.yaml without a connector module: {', '.join(unregistered)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="probe", description=__doc__)
    parser.add_argument("ds_ids", nargs="*", metavar="DS-ID", help="DS-IDs, or 'all'")
    parser.add_argument("--tier", help="every source of this tier (P0, P1, P2)")
    parser.add_argument("--list", action="store_true", help="list sources and key status")
    parser.add_argument(
        "--card",
        action="store_true",
        help="only regenerate cards from the latest runs (no network)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="print the PROBE_REPORT summary table for the chosen sources",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=f"probe even if the last run is younger than {REPROBE_GUARD}",
    )
    parser.add_argument(
        "--reset-samples",
        action="store_true",
        help="delete the source's committed samples before probing",
    )
    args = parser.parse_args(argv)

    if args.list:
        _list()
        return 0
    available = connectors()
    targets = [d.upper() for d in args.ds_ids]
    if "ALL" in targets:
        targets = [d for d in available if latest_run(d) is not None]
    if args.tier:
        targets += [
            d
            for d, e in registry().items()
            if e.get("tier") == args.tier.upper() and d in available
        ]
    if not targets:
        parser.error("name at least one DS-ID (or 'all'), or use --tier / --list")
    unknown = [d for d in targets if d not in available]
    if unknown:
        parser.error(f"no connector module for {', '.join(unknown)}")
    targets = list(dict.fromkeys(targets))
    if args.summary:
        print(summary_table(targets))
        return 0

    settings = get_settings()
    failed = []
    for ds_id in targets:
        connector = available[ds_id]
        if not args.card:
            if recently_probed(ds_id, REPROBE_GUARD) and not args.force:
                print(f"{ds_id}: probed within the last hour; skipping (use --force)")
            else:
                print(f"{ds_id} · {connector.title}")
                if args.reset_samples:
                    clear_samples(ds_id)
                try:
                    summary = run_probe(connector, settings, min_interval_s=min_interval_s(ds_id))
                except Exception as exc:
                    print(f"  {ds_id}: probe crashed: {type(exc).__name__}: {exc}", file=sys.stderr)
                    failed.append(ds_id)
                    continue
                if summary["needs_you"]:
                    print(f"  needs you: {', '.join(summary['needs_you'])}")
        if write_card(connector):
            print(f"  card written: {card_path(ds_id).relative_to(card_path(ds_id).parents[2])}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
