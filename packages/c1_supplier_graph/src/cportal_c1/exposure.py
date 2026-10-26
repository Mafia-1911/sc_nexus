"""Time to survive (TTS), time to recover (TTR) and performance impact (C1 §5, L0), after
Simchi-Levi, Schmidt & Wei (2014) "From superstorms to factory fires", HBR, and Simchi-Levi et al.
(2015) "Identifying risks and mitigating disruptions in the automotive supply chain".

TTS of node j: the longest time t the network can still meet every plant's open-order output
with j down, using input inventory and the spare capacity of other *qualified* suppliers.
One LP (HiGHS) with variables t, flows x on supply relationships and production y:

    max t  s.t.  d·t ≤ y                       (demand, finished goods at each plant)
                 Σ bom·y - Σ x_in ≤ inventory  (inputs at each plant)
                 Σ x_out ≤ y ≤ capacity·t      (each supplier's output)
                 x, y = 0 for j's output; flows through j (the gateway) = 0

Performance impact: the value of output that cannot be made during j's TTR (same constraints,
t fixed to TTR, minimise the value of unmet demand). TTS < TTR flags a node whose recovery
outlasts the network's buffers. TTR comes from priors by node type, or from a linked event.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, csr_matrix

from cportal_c1.graph import SupplyGraph


@dataclass(frozen=True)
class Exposure:
    tts_d: float
    tts_capped: bool  # the network survives the whole cap (reported as "≥ cap")
    ttr_d: float
    ttr_p90_d: float
    ttr_source: str  # "prior" | "event"
    performance_impact_usd: float


class ExposureModel:
    """Builds the constraint matrices once per graph; each node is a change of bounds."""

    def __init__(self, g: SupplyGraph) -> None:
        self.g = g
        self.cap = g.priors.tts_cap_d
        self.x = {s.id: i for i, s in enumerate(g.supplies)}
        pairs = sorted({(f, p) for f, ps in g.makes.items() for p in ps})
        self.y = {pair: len(self.x) + i for i, pair in enumerate(pairs)}
        self.owner = {col: f for (f, _), col in self.y.items()}
        self.n = len(self.x) + len(self.y)
        self.demand = [(pair, d) for pair, d in sorted(g.demand.items()) if d > 0]
        rows: list[tuple[list[int], list[float], float]] = []  # (cols, coefs, rhs) over x, y
        uses: dict[tuple[str, str], list[tuple[int, float]]] = {}
        for (f, p), col in self.y.items():
            for c, qty in g.bom.get(p, {}).items():
                uses.setdefault((f, c), []).append((col, qty))
        for (f, c), suppliers in g.inbound.items():
            if (f, c) not in uses:
                continue
            cols = [col for col, _ in uses[(f, c)]] + [self.x[s.id] for s in suppliers]
            coefs = [qty for _, qty in uses[(f, c)]] + [-1.0] * len(suppliers)
            rows.append((cols, coefs, g.inventory.get((f, c), 0.0)))
        for (s, c), out in g.outbound.items():
            if (s, c) in self.y:
                cols = [self.x[e.id] for e in out] + [self.y[(s, c)]]
                rows.append((cols, [1.0] * len(out) + [-1.0], 0.0))
        self.balance = rows
        self.capacity = [
            (self.y[(s, c)], cap) for (s, c), cap in g.capacity.items() if (s, c) in self.y
        ]

    # --- problem assembly ---------------------------------------------------------------

    def _bounds(self, removed: frozenset[str]) -> list[tuple[float, float | None]]:
        g = self.g
        blocking = {n for n in removed if g.nodes.get(n) is None or g.nodes[n].type != "hub"}
        bounds: list[tuple[float, float | None]] = [(0.0, None)] * self.n
        for s in g.supplies:
            if s.src in blocking or blocking.intersection(s.route):
                bounds[self.x[s.id]] = (0.0, 0.0)
        for (f, _), col in self.y.items():
            if f in blocking:
                bounds[col] = (0.0, 0.0)
        return bounds

    def _tts(self, removed: frozenset[str], factor: dict[str, float]) -> float:
        """Max t; columns are [t, x…, y…]."""
        cols: list[int] = []
        data: list[float] = []
        rhs: list[float] = []
        r = 0
        for (f, p), d in self.demand:  # d·t - y ≤ 0
            cols += [0, 1 + self.y[(f, p)]]
            data += [d, -1.0]
            rhs.append(0.0)
            r += 1
        rows_idx = [i for i in range(len(self.demand)) for _ in range(2)]
        for bcols, coefs, b in self.balance:
            cols += [1 + c for c in bcols]
            data += coefs
            rows_idx += [r] * len(bcols)
            rhs.append(b)
            r += 1
        for col, cap in self.capacity:  # y - cap·t ≤ 0
            cols += [1 + col, 0]
            data += [1.0, -cap * factor.get(self.owner[col], 1.0)]
            rows_idx += [r, r]
            rhs.append(0.0)
            r += 1
        a = csr_matrix(coo_matrix((data, (rows_idx, cols)), shape=(r, 1 + self.n)))
        bounds = [(0.0, self.cap), *self._bounds(removed)]
        c = np.zeros(1 + self.n)
        c[0] = -1.0
        res = linprog(c, A_ub=a, b_ub=np.array(rhs), bounds=bounds, method="highs")
        return float(res.x[0]) if res.status == 0 else 0.0

    def _impact(self, removed: frozenset[str], horizon: float) -> float:
        """Min value of output not made within `horizon` days. Columns are [x…, y…, u…]."""
        g = self.g
        k = len(self.demand)
        cols: list[int] = []
        data: list[float] = []
        rows_idx: list[int] = []
        rhs: list[float] = []
        r = 0
        for i, ((f, p), d) in enumerate(self.demand):  # -y - u ≤ -d·T
            cols += [self.y[(f, p)], self.n + i]
            data += [-1.0, -1.0]
            rows_idx += [r, r]
            rhs.append(-d * horizon)
            r += 1
        for bcols, coefs, b in self.balance:
            cols += bcols
            data += coefs
            rows_idx += [r] * len(bcols)
            rhs.append(b)
            r += 1
        a = csr_matrix(coo_matrix((data, (rows_idx, cols)), shape=(r, self.n + k)))
        bounds = self._bounds(removed) + [(0.0, None)] * k
        for col, cap in self.capacity:
            lo, hi = bounds[col]
            bounds[col] = (lo, cap * horizon if hi is None else min(hi, cap * horizon))
        c = np.zeros(self.n + k)
        for i, ((_, p), _) in enumerate(self.demand):
            c[self.n + i] = g.products[p].unit_value_usd
        res = linprog(c, A_ub=a, b_ub=np.array(rhs), bounds=bounds, method="highs")
        return float(res.fun) if res.status == 0 else self._all_value(horizon)

    def _all_value(self, horizon: float) -> float:
        return sum(d * horizon * self.g.products[p].unit_value_usd for (_, p), d in self.demand)

    # --- public -------------------------------------------------------------------------

    def ttr(self, node: str) -> tuple[float, float, str]:
        g = self.g
        events = [e for e in g.events.get(node, []) if e.duration_d]
        if events:
            longest = max(float(e.duration_d or 0.0) for e in events)
            return longest, longest * 1.6, "event"
        p50, p90 = g.priors.ttr(g.nodes[node].type)
        return p50, p90, "prior"

    def tts(self, removed: frozenset[str], factor: dict[str, float] | None = None) -> float:
        if self.g.gateway in removed and (factor or {}).get(self.g.gateway, 0.0) == 0.0:
            return 0.0  # exports stop at once; goods already at sea are not demand here
        return max(0.0, round(self._tts(removed, factor or {}), 2))

    def exposure(self, node: str) -> Exposure:
        ttr, ttr_p90, source = self.ttr(node)
        removed = frozenset({node})
        tts = self.tts(removed)
        impact = self._all_value(ttr) if node == self.g.gateway else self._impact(removed, ttr)
        return Exposure(
            tts_d=tts,
            tts_capped=tts >= self.cap - 1e-6,
            ttr_d=ttr,
            ttr_p90_d=ttr_p90,
            ttr_source=source,
            performance_impact_usd=round(max(impact, 0.0), 2),
        )
