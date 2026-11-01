"""`uv run c5 eval|inspect`: C5 on the host (the heavy image work never runs in a request)."""

from __future__ import annotations

import argparse
import json
import sys
import time

from cportal_core.db import session_scope
from cportal_core.paths import repo_root

from cportal_c5 import datasets, gallery, store
from cportal_c5.config import load_config
from cportal_c5.evaluate import deploy_method, evaluate
from cportal_c5.vision import Encoder

REPORT = repo_root() / "docs" / "model-cards" / "c5-eval.json"


def run_eval(categories: list[str], database_url: str | None, write_db: bool) -> int:
    cfg = load_config()
    encoder = Encoder(side=int(cfg["vision"]["side"]))
    reports = json.loads(REPORT.read_text()) if REPORT.exists() else {}
    shots = max(int(k) for k in cfg["vision"]["shots"])
    for category in categories:
        if not datasets.available(category):
            print(f"{category}: images missing (uv run vis-fetch)")
            continue
        t0 = time.perf_counter()
        report, results, feats, items = evaluate(category, encoder)
        method = deploy_method(report)
        report["deploy"] = method
        test = [i for i in items if i.split == "test"]
        refs = [i for i in items if i.split == "ref"][:shots]
        live = results[f"few_shot_k{shots}"]
        gallery.save_bank(
            category, [feats[str(i.path)] for i in refs], live.name, live.threshold,
            {"side": encoder.side, "tile": cfg["categories"][category].get("tile"),
             "image_auroc": live.metrics["image_auroc"]},
        )  # fmt: skip
        images = gallery.write(category, test, results[method])
        if write_db:
            with session_scope(database_url) as session:
                print(category, store.save_category(session, category, report, method, images))
        report["seconds"] = round(time.perf_counter() - t0, 1)
        reports[category] = report
        REPORT.write_text(json.dumps(reports, indent=1) + "\n")
        summary = {
            m: (r["image_auroc"], r["pixel_auroc"], r["recall_at_fpr"])
            for m, r in report["methods"].items()
        }
        print(
            f"{category}: deploy {method}; (AUROC, pixel AUROC, recall@FPR) {summary}", flush=True
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="c5", description=__doc__.split("\n")[0])
    parser.add_argument("--database-url")
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("eval", help="evaluate zero/few-shot per category, write gallery and banks")
    e.add_argument("categories", nargs="*", default=list(load_config()["categories"]))
    e.add_argument("--no-db", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "eval":
        return run_eval(args.categories, args.database_url, not args.no_db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
