"""C2 evaluation on the gold set (C2-AC01, AC02, AC04): rules, an LLM, and both combined."""

from __future__ import annotations

import csv
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cportal_core.llm import LLMProvider

from cportal_c2.extract import extract
from cportal_c2.llm import SCHEMA, SYSTEM, ground


@dataclass(frozen=True)
class Gold:
    article_id: str
    text: str
    published: datetime
    relevant: bool
    types: frozenset[str]


@dataclass
class Score:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    type_hits: int = 0
    by_type: Counter[str] = field(default_factory=Counter)

    def add(self, gold: Gold, predicted: bool, ptype: str | None) -> None:
        if predicted and gold.relevant:
            self.tp += 1
            self.type_hits += ptype in gold.types
        elif predicted:
            self.fp += 1
        elif gold.relevant:
            self.fn += 1
        else:
            self.tn += 1

    def report(self) -> dict[str, float]:
        p = self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0
        r = self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        return {
            "precision": round(p, 3),
            "recall": round(r, 3),
            "f1": round(f1, 3),
            "type_accuracy_on_hits": round(self.type_hits / self.tp, 3) if self.tp else 0.0,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
        }


def load_gold(path: Path) -> list[Gold]:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    return [
        Gold(
            article_id=r["article_id"],
            text=r["text"],
            published=datetime.fromisoformat(r["published"]).replace(tzinfo=UTC)
            if r["published"]
            else datetime.now(UTC),
            relevant=r["relevant"] == "y",
            types=frozenset(t for t in r["types"].split("|") if t),
        )
        for r in rows
    ]


def evaluate(gold: list[Gold], provider: LLMProvider | None = None) -> dict[str, Any]:
    rules, llm, combined = Score(), Score(), Score()
    ungrounded = asked = 0
    seconds = 0.0
    for g in gold:
        x = extract(g.article_id, g.text, None, g.published)
        rules.add(g, x.is_supply_chain_disruption, x.event_type)
        if provider is None:
            continue
        t0 = time.perf_counter()
        verdict, dropped = ground(provider.json(SYSTEM, g.text, SCHEMA), g.text)
        seconds += time.perf_counter() - t0
        asked += 1
        ungrounded += dropped
        llm.add(g, verdict["is_supply_chain_disruption"], verdict.get("event_type"))
        # The production merge (A-061): rules decide, a grounded LLM "yes" with a place rescues.
        rescue = verdict["is_supply_chain_disruption"] and bool(x.locations)
        combined.add(
            g,
            x.is_supply_chain_disruption or rescue,
            verdict.get("event_type") if rescue else x.event_type,
        )
    out: dict[str, Any] = {
        "gold": {"articles": len(gold), "relevant": sum(g.relevant for g in gold)},
        "rules": rules.report(),
    }
    if provider is not None:
        out[f"llm:{provider.model}"] = {
            **llm.report(),
            "ungrounded_fields": ungrounded,
            "seconds_per_article": round(seconds / max(asked, 1), 1),
        }
        out[f"rules+llm:{provider.model}"] = combined.report()
    return out
