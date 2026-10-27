"""Local-LLM verdicts for the top-K articles (C2 §5.3, Q-03): constrained JSON, then grounding.

The model must quote its evidence verbatim; a field whose quote is not in the text is dropped
and counted as ungrounded (C2 §4). Verdicts are stored as `prediction` rows (capability c2,
target "article") so any process — the host with Ollama, or the worker — can merge them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid5

from cportal_core.enums import DisruptionType
from cportal_core.llm import LLMProvider
from cportal_core.models import Article, Prediction
from sqlalchemy import select
from sqlalchemy.orm import Session

from cportal_c2 import LLM_VERSION
from cportal_c2.cluster import NS
from cportal_c2.config import Config, load_config
from cportal_c2.extract import Extraction, article_text, extract

SYSTEM = (
    "You read one news item and decide whether it reports a disruption to physical supply "
    "chains, ports, shipping, factories or freight (not politics, finance or crime in general). "
    "Quote evidence word for word from the text; use an empty string when the text has none."
)
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_supply_chain_disruption": {"type": "boolean"},
        "event_type": {"type": "string", "enum": [t.value for t in DisruptionType]},
        "event_type_evidence": {"type": "string"},
        "locations": {"type": "array", "items": {"type": "string"}},
        "status": {"type": "string", "enum": ["reported", "ongoing", "resolved"]},
        "status_evidence": {"type": "string"},
        "duration_text": {"type": "string"},
    },
    "required": [
        "is_supply_chain_disruption",
        "event_type",
        "event_type_evidence",
        "locations",
        "status",
    ],
}


def ground(raw: dict[str, Any], text: str) -> tuple[dict[str, Any], int]:
    """Keep only fields whose quotes are in the text. Returns (verdict, ungrounded count)."""
    low = text.lower()

    def found(quote: Any) -> bool:
        return isinstance(quote, str) and bool(quote.strip()) and quote.strip().lower() in low

    out: dict[str, Any] = {
        "is_supply_chain_disruption": bool(raw.get("is_supply_chain_disruption"))
    }
    dropped = 0
    if found(raw.get("event_type_evidence")):
        out["event_type"] = raw.get("event_type")
        out["event_type_evidence"] = raw["event_type_evidence"].strip()
    else:
        dropped += 1
    locations = [loc for loc in raw.get("locations") or [] if found(loc)]
    dropped += len(raw.get("locations") or []) - len(locations)
    out["locations"] = locations
    if found(raw.get("status_evidence")):
        out["status"] = raw.get("status")
    elif raw.get("status_evidence"):
        dropped += 1
    if found(raw.get("duration_text")):
        out["duration_text"] = raw["duration_text"].strip()
    # A positive verdict needs grounded type evidence; otherwise it does not count.
    if out["is_supply_chain_disruption"] and "event_type" not in out:
        out["is_supply_chain_disruption"] = False
    return out, dropped


def candidates(
    session: Session, since: datetime, k: int, cfg: Config
) -> list[tuple[Article, Extraction]]:
    done = set(
        session.scalars(
            select(Prediction.target_id).where(
                Prediction.capability == "c2", Prediction.target_type == "article"
            )
        )
    )
    rows = session.scalars(
        select(Article).where(Article.is_synthetic.is_(False), Article.published_at >= since)
    ).all()
    scored = [
        (a, extract(str(a.id), a.title, a.snippet, a.published_at, cfg))
        for a in rows
        if a.id not in done
    ]
    # Positives and near misses: the LLM confirms, rejects or rescues them.
    pool = [(a, x) for a, x in scored if x.relevance >= 0.45]
    pool.sort(key=lambda ax: (-ax[1].relevance, -(ax[0].published_at or since).timestamp()))
    return pool[:k]


def run(session: Session, provider: LLMProvider, since: datetime, k: int = 10) -> dict[str, int]:
    cfg = load_config()
    stats = {"asked": 0, "positive": 0, "ungrounded_fields": 0}
    for article, rules in candidates(session, since, k, cfg):
        text = article_text(article.title, article.snippet)
        raw = provider.json(SYSTEM, text, SCHEMA)
        verdict, dropped = ground(raw, text)
        stats["asked"] += 1
        stats["positive"] += verdict["is_supply_chain_disruption"]
        stats["ungrounded_fields"] += dropped
        session.merge(
            Prediction(
                id=uuid5(NS, f"llm:{article.id}:{provider.model}"),
                source_id="c2",
                source_record_id=str(article.id),
                data_mode=article.data_mode,
                is_synthetic=False,
                generator_version=LLM_VERSION,
                capability="c2",
                target_type="article",
                target_id=article.id,
                as_of=datetime.now(UTC),
                value=1.0 if verdict["is_supply_chain_disruption"] else 0.0,
                explanation={
                    "model": provider.model,
                    "verdict": verdict,
                    "raw": raw,
                    "ungrounded": dropped,
                    "rules": {"relevance": rules.relevance, "event_type": rules.event_type},
                },
                features_hash=provider.model,
            )
        )
        session.commit()  # one article at a time: a slow model never loses finished work
    return stats


def verdicts(session: Session, article_ids: list[UUID]) -> dict[str, dict[str, Any]]:
    rows = session.scalars(
        select(Prediction).where(
            Prediction.capability == "c2",
            Prediction.target_type == "article",
            Prediction.target_id.in_(article_ids),
        )
    )
    return {str(p.target_id): p.explanation for p in rows}


def apply(x: Extraction, verdict: dict[str, Any]) -> Extraction:
    """Merge a grounded LLM verdict as a second opinion (A-061): a "no" lowers confidence but
    does not delete what the rules found; a grounded "yes" confirms it or rescues a near miss."""
    v = verdict["verdict"]
    update: dict[str, Any] = {"extractor": f"rules+llm:{verdict['model']}"}
    if not v["is_supply_chain_disruption"]:
        update["llm_agrees"] = False
        update["confidence"] = round(x.confidence * 0.6, 2)
        return x.model_copy(update=update)
    update["llm_agrees"] = True
    if x.locations:  # an event needs a known place; the gazetteer still decides where
        update["is_supply_chain_disruption"] = True
        update["event_type"] = v.get("event_type", x.event_type)
        if v.get("status"):
            update["status"] = v["status"]
        update["confidence"] = max(x.confidence, 0.7)
    return x.model_copy(update=update)
