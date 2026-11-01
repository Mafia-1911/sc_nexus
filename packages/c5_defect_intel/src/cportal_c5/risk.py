"""Defective-lot risk and SPC per line (C5 §6.3, C5-AC05).

**Forecast.** Confirmed-defect counts per lot, beta-binomial with empirical Bayes: an industry
prior (method of moments on training lots), a plant posterior, then the line's own lots on top,
all weighted by recency (half-life 14 days) so a drifting line shows quickly. The next lot's
rate varies around that mean (between-lot dispersion κ, method of moments), so P(the next lot
fails) = P(Y > Ac), Y ~ BetaBinomial(n, m κ, (1 - m) κ) for the lot's plan. Baseline: the industry's
historical failure rate. Scored by Brier score and reliability on the last `test_days`, each
lot predicted from earlier lots only.

**SPC.** Per line, a p-chart (centre from the line's earlier lots, 3σ limits per sample size)
and an EWMA (λ from config) with its own limit; points above either raise an alarm.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import numpy as np
from cportal_core.models import Batch, Product
from scipy.stats import betabinom
from sqlalchemy import select
from sqlalchemy.orm import Session

from cportal_c5.config import load_config

HALF_LIFE_D = 14.0
LINE_STRENGTH = 300.0  # prior items a line's own evidence must outweigh


@dataclass(frozen=True)
class Lot:
    id: UUID
    facility_id: UUID
    line: str
    industry: str
    produced_at: datetime
    n: int
    accept: int
    confirmed: int
    failed: bool

    @property
    def line_key(self) -> str:
        return f"{self.facility_id}.{self.line}"


def load_lots(session: Session, scenario_id: UUID | None = None) -> list[Lot]:
    q = (
        select(Batch, Product.sku)
        .join(Product, Product.id == Batch.product_id)
        .where(Batch.lot_code.like("FG-%"), Batch.status != "in_process")
        .order_by(Batch.produced_at)
    )
    if scenario_id is not None:
        q = q.where(Batch.scenario_id == scenario_id)
    out = []
    for b, sku in session.execute(q).all():
        r = b.aql_result or {}
        if "confirmed_defects" not in r:
            continue
        industry = "pharma" if sku.startswith("P-") else "garments"
        out.append(
            Lot(
                b.id, b.facility_id, b.line or "?", industry, b.produced_at,
                int(r["sample_size"]), int(r["accept"]), int(r["confirmed_defects"]),
                r.get("aql_verdict") == "reject",
            )
        )  # fmt: skip
    return out


def _weight(age_days: float) -> float:
    return math.pow(0.5, max(age_days, 0.0) / HALF_LIFE_D)


def industry_prior(lots: list[Lot]) -> tuple[float, float]:
    """Beta(a, b) of per-lot defect fractions by the method of moments (strength ≥ 50)."""
    p = np.array([lot.confirmed / lot.n for lot in lots]) if lots else np.array([0.01])
    m = float(np.clip(p.mean(), 1e-4, 0.5))
    v = float(max(p.var(), 1e-8))
    k = max(m * (1 - m) / v - 1, 50.0)
    return m * k, (1 - m) * k


def lot_dispersion(lots: list[Lot]) -> float:
    """Concentration κ of lot rates around their line's mean (between-lot variance beyond
    binomial noise, method of moments); small κ = lots vary a lot."""
    by_line: dict[str, list[Lot]] = defaultdict(list)
    for lot in lots:
        by_line[lot.line_key].append(lot)
    resid, noise, means = [], [], []
    for rows in by_line.values():
        if len(rows) < 3:
            continue
        m = sum(r.confirmed for r in rows) / sum(r.n for r in rows)
        means.append(m)
        for r in rows:
            resid.append((r.confirmed / r.n - m) ** 2)
            noise.append(m * (1 - m) / r.n)
    if not resid:
        return 100.0
    between = max(float(np.mean(resid) - np.mean(noise)), 1e-6)
    m = float(np.mean(means))
    return float(np.clip(m * (1 - m) / between - 1, 5.0, 2000.0))


class RiskModel:
    def __init__(self, history: list[Lot], fit: list[Lot] | None = None) -> None:
        """`history`: lots the posteriors may read (only those before each prediction time);
        `fit`: lots the industry prior and dispersion are estimated on (default: history)."""
        self.history = sorted(history, key=lambda lot: lot.produced_at)
        fit = fit if fit is not None else self.history
        industries = {lot.industry for lot in self.history}
        self.prior = {
            ind: industry_prior([lot for lot in fit if lot.industry == ind]) for ind in industries
        }
        self.kappa = {
            ind: lot_dispersion([lot for lot in fit if lot.industry == ind]) for ind in industries
        }

    def posterior(
        self, line_key: str, facility_id: UUID, industry: str, at: datetime
    ) -> tuple[float, float]:
        a0, b0 = self.prior.get(industry, (1.0, 99.0))
        plant_c = plant_n = line_c = line_n = 0.0
        for lot in self.history:
            if lot.produced_at >= at:
                break
            if lot.facility_id != facility_id:
                continue
            w = _weight((at - lot.produced_at).total_seconds() / 86_400)
            plant_c += w * lot.confirmed
            plant_n += w * lot.n
            if lot.line_key == line_key:
                line_c += w * lot.confirmed
                line_n += w * lot.n
        plant_rate = (a0 + plant_c) / (a0 + b0 + plant_n)
        return LINE_STRENGTH * plant_rate + line_c, LINE_STRENGTH * (1 - plant_rate) + (
            line_n - line_c
        )

    def p_fail(
        self, line_key: str, facility_id: UUID, industry: str, at: datetime, n: int, accept: int
    ) -> float:
        a, b = self.posterior(line_key, facility_id, industry, at)
        m, k = a / (a + b), self.kappa.get(industry, 100.0)
        return float(betabinom.sf(accept, n, m * k, (1 - m) * k))  # the next lot varies too


def evaluate(lots: list[Lot], test_days: int | None = None) -> dict[str, Any]:
    """C5-AC05: Brier and reliability on the last `test_days`, vs the historical base rate."""
    test_days = test_days or int(load_config()["risk"]["test_days"])
    if not lots:
        return {"n": 0}
    end = max(lot.produced_at for lot in lots)
    cut = end - timedelta(days=test_days)
    train = [lot for lot in lots if lot.produced_at < cut]
    test = [lot for lot in lots if lot.produced_at >= cut]
    model = RiskModel(lots, fit=train)  # priors from train; each lot sees only earlier lots
    base = {
        ind: (sum(lot.failed for lot in train if lot.industry == ind) + 0.5)
        / (sum(1 for lot in train if lot.industry == ind) + 1)
        for ind in {lot.industry for lot in lots}
    }
    pred = np.array(
        [
            model.p_fail(
                lot.line_key, lot.facility_id, lot.industry, lot.produced_at, lot.n, lot.accept
            )
            for lot in test
        ]
    )
    naive = np.array([base[lot.industry] for lot in test])
    y = np.array([lot.failed for lot in test], dtype=float)
    bins = []
    for lo in np.arange(0, 1, 0.2):
        m = (pred >= lo) & (pred < lo + 0.2 if lo < 0.8 else pred <= 1.0)
        if m.any():
            bins.append(
                {
                    "bin": f"{lo:.1f}–{lo + 0.2:.1f}",
                    "n": int(m.sum()),
                    "predicted": round(float(pred[m].mean()), 3),
                    "observed": round(float(y[m].mean()), 3),
                }
            )
    return {
        "n_train": len(train),
        "n_test": len(test),
        "test_failures": int(y.sum()),
        "brier": round(float(np.mean((pred - y) ** 2)), 4),
        "brier_base_rate": round(float(np.mean((naive - y) ** 2)), 4),
        "base_rate": {k: round(v, 4) for k, v in base.items()},
        "reliability": bins,
    }


def spc(lots: list[Lot], baseline_days: int = 14) -> dict[str, dict[str, Any]]:
    """p-chart and EWMA per line, with alarms."""
    lam = float(load_config()["risk"]["ewma_lambda"])
    by_line: dict[str, list[Lot]] = defaultdict(list)
    for lot in lots:
        by_line[lot.line_key].append(lot)
    out = {}
    for key, rows in by_line.items():
        rows.sort(key=lambda lot: lot.produced_at)
        end = rows[-1].produced_at
        base = [r for r in rows if r.produced_at < end - timedelta(days=baseline_days)] or rows
        p_bar = max(sum(r.confirmed for r in base) / sum(r.n for r in base), 1e-4)
        n_bar = float(np.mean([r.n for r in rows]))
        sigma_e = math.sqrt(p_bar * (1 - p_bar) / n_bar) * math.sqrt(lam / (2 - lam))
        z, points, alarms = p_bar, [], 0
        for r in rows:
            p = r.confirmed / r.n
            ucl = p_bar + 3 * math.sqrt(p_bar * (1 - p_bar) / r.n)
            z = lam * p + (1 - lam) * z
            alarm = p > ucl or z > p_bar + 3 * sigma_e
            alarms += alarm
            points.append({
                "batch_id": str(r.id), "produced_at": r.produced_at.isoformat(), "p": round(p, 5),
                "ucl": round(ucl, 5), "ewma": round(z, 5), "alarm": bool(alarm), "failed": r.failed,
            })  # fmt: skip
        out[key] = {
            "facility_id": str(rows[0].facility_id), "line": rows[0].line,
            "industry": rows[0].industry, "center": round(p_bar, 5),
            "ewma_ucl": round(p_bar + 3 * sigma_e, 5), "alarms": alarms,
            "alarm_now": points[-1]["alarm"], "points": points,
        }  # fmt: skip
    return out
