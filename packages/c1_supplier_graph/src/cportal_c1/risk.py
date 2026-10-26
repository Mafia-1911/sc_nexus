"""Risk baseline (C1 §5, L1): a transparent weighted score every learned model must beat.

risk = 100 × Σ wᵢ·xᵢ with features xᵢ in 0–1 and weights from `config/priors/c1.yaml`:
impact (dominance, reach, TTS gap) and likelihood (hazard exposure, lot quality, linked
events). Because the score is additive, each feature's contribution against the average node,
100·wᵢ·(xᵢ - mean xᵢ), is its exact Shapley value; the drivers shown in the UI are these.
Country risk joins when a WGI source works (DS-RISK-01's sample is an error response).
"""

from __future__ import annotations

from dataclasses import dataclass

from cportal_c1.graph import SupplyGraph

LABELS = {
    "dominance": "Single point of failure",
    "reach": "Open orders that depend on it",
    "tts_gap": "Recovery outlasts the network's buffers",
    "hazard": "Cyclone and flood exposure (estimate)",
    "quality": "Lots rejected at AQL (30 days)",
    "events": "Open disruption events linked",
}


@dataclass(frozen=True)
class Scored:
    score: float
    band: str
    features: dict[str, float]
    contributions: dict[str, float]


def features(
    g: SupplyGraph,
    node: str,
    *,
    dominated_value: float,
    downstream_value: float,
    industry_value: float,
    tts: float | None,
    ttr: float | None,
) -> dict[str, float]:
    n = g.nodes[node]
    lots, rejected = g.quality.get(node, (0, 0))
    events = [e for e in g.events.get(node, [])]
    gap = 0.0
    if tts is not None and ttr:
        gap = min(1.0, max(0.0, (ttr - tts) / ttr))
    total = industry_value or 1.0
    return {
        "dominance": min(1.0, dominated_value / total),
        "reach": min(1.0, downstream_value / total),
        "tts_gap": gap,
        "hazard": g.priors.hazard(n.type, n.cluster, overseas=n.country != "BD"),
        "quality": rejected / lots if lots else 0.0,
        "events": max((e.severity * e.confidence for e in events), default=0.0),
    }


def score(g: SupplyGraph, table: dict[str, dict[str, float]]) -> dict[str, Scored]:
    """Scores and exact contributions for every node in `table` (node → features)."""
    weights = g.priors.risk_weights
    bands = g.priors.risk_bands
    if not table:
        return {}
    mean = {k: sum(f[k] for f in table.values()) / len(table) for k in weights}
    out: dict[str, Scored] = {}
    for node, feats in table.items():
        value = 100 * sum(weights[k] * feats[k] for k in weights)
        band = "high" if value >= bands["high"] else "medium" if value >= bands["medium"] else "low"
        out[node] = Scored(
            score=round(value, 1),
            band=band,
            features={k: round(v, 4) for k, v in feats.items()},
            contributions={k: round(100 * weights[k] * (feats[k] - mean[k]), 2) for k in weights},
        )
    return out
