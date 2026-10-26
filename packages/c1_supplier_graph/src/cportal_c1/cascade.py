"""Cascade what-if (C1 §5, L0): disrupt nodes for N days and follow the shortage, day by day.

Each day, suppliers ship normal volumes (capacity × the disruption's capacity factor, and their
own inputs permitting); shipments reach the plant after their physical transit, later if the
supplier runs late, if the Chattogram gateway is closed when they arrive, or if their hub is
closed (reroute). Plants make each order's daily output from input inventory; what they cannot
make becomes backlog, caught up at `surge` × normal once inputs return. After `ramp_d` days,
plants re-source a shortfall from other *qualified* suppliers up to those suppliers' spare
capacity. Only the part of the network that depends on a disrupted node is simulated: the rest
runs in steady state by construction.

Order impact: an order must leave the plant `export_lead_d` days before its due date. Its delay
is the plant's backlog (in days of output) at that moment plus any wait at the closed gateway;
it is late beyond `order_slack_d`. Everything is deterministic for a given seed.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field

from cportal_c1.graph import Supply, SupplyGraph


@dataclass(frozen=True)
class Disruption:
    node: str
    duration_d: float
    capacity_pct: float = 0.0  # remaining capacity during the disruption
    start_d: float = 0.0
    extra_lead_time_d: float = 0.0  # shipments made during the window arrive this much later

    def active(self, day: float) -> bool:
        return self.start_d <= day < self.start_d + self.duration_d

    @property
    def end_d(self) -> float:
        return self.start_d + self.duration_d


@dataclass(frozen=True)
class OrderImpact:
    order_id: str
    reference: str
    buyer: str
    product: str
    facility: str
    due: str
    revenue_usd: float
    delay_d: float
    late: bool
    cause: str  # "inputs" | "gateway" | "plant"


@dataclass
class Outcome:
    timeline: list[dict[str, float]] = field(default_factory=list)
    impacts: list[OrderImpact] = field(default_factory=list)
    first_impact_d: float | None = None
    recovery_d: float | None = None

    @property
    def late(self) -> list[OrderImpact]:
        return [i for i in self.impacts if i.late]

    @property
    def revenue_at_risk_usd(self) -> float:
        return round(sum(i.revenue_usd for i in self.late), 2)


@dataclass(frozen=True)
class Noise:
    """Monte Carlo draws: one per run (C1 §5 L1)."""

    duration: dict[str, float]
    extra_lead: dict[str, float]
    transit: float
    ramp: float

    @staticmethod
    def none() -> Noise:
        return Noise({}, {}, 1.0, 1.0)

    @staticmethod
    def draw(rng: random.Random, disruptions: list[Disruption]) -> Noise:
        return Noise(
            duration={d.node: rng.lognormvariate(0.0, 0.35) for d in disruptions},
            extra_lead={d.node: rng.lognormvariate(0.0, 0.3) for d in disruptions},
            transit=rng.uniform(0.9, 1.25),
            ramp=rng.uniform(0.6, 1.5),
        )


def simulate(g: SupplyGraph, disruptions: list[Disruption], noise: Noise | None = None) -> Outcome:
    noise = noise or Noise.none()
    pri = g.priors
    disruptions = [
        Disruption(
            node=d.node,
            duration_d=d.duration_d * noise.duration.get(d.node, 1.0),
            capacity_pct=d.capacity_pct,
            start_d=d.start_d,
            extra_lead_time_d=d.extra_lead_time_d * noise.extra_lead.get(d.node, 1.0),
        )
        for d in disruptions
    ]
    by_node = {d.node: d for d in disruptions}
    hit = set(by_node)
    ramp = pri.ramp_d * noise.ramp

    def factor(node: str, day: float) -> float:
        d = by_node.get(node)
        return d.capacity_pct / 100 if d and d.active(day) else 1.0

    gateway = by_node.get(g.gateway)
    hubs_closed = {n: d for n, d in by_node.items() if g.nodes.get(n) and g.nodes[n].type == "hub"}
    lost = gateway.duration_d * (1 - gateway.capacity_pct / 100) if gateway else 0.0
    clearing = math.ceil(lost * pri.gateway_clearing_ratio)

    def gateway_wait(day: float) -> float:
        """Days a box reaching Chattogram on `day` waits (closure plus the backlog it leaves)."""
        if gateway is None or day < gateway.start_d:
            return 0.0
        closed_until = gateway.start_d + lost
        if day < closed_until:
            return closed_until - day + clearing
        if day < closed_until + clearing:
            return closed_until + clearing - day
        return 0.0

    # --- the part of the network that depends on a disrupted node -----------------------
    affected = {
        (f, c) for (f, c) in g.inbound if g.need.get((f, c), 0.0) > 0 and hit & g.input_deps(f, c)
    }
    producers = {
        (f, p)
        for (f, p), rate in g.production.items()
        if rate > 0 and (f in hit or any((f, c) in affected for c in g.bom.get(p, {})))
    }
    feeding: dict[tuple[str, str], list[Supply]] = defaultdict(list)
    for f, c in affected:
        for s in g.inbound[(f, c)]:
            feeding[(s.src, c)].append(s)
    supplier_pairs = sorted(feeding)
    transit = {
        s.id: max(1, round(s.transit_d * noise.transit)) for k in affected for s in g.inbound[k]
    }
    horizon = pri.horizon_d + 60
    end_all = max((d.end_d for d in disruptions), default=0.0)
    lag = max((d.extra_lead_time_d for d in disruptions), default=0.0)
    settle = end_all + max(transit.values(), default=1) + lag + 2

    inv = {k: g.inventory.get(k, g.need[k] * pri.default_cover_d) for k in affected}
    pipeline: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for k in affected:
        for s in g.inbound[k]:
            for day in range(transit[s.id]):  # steady state: goods already on the way
                pipeline[s.id][day] += g.flow(s)
    backlog: dict[tuple[str, str], float] = defaultdict(float)
    backlog_series: dict[tuple[str, str], list[float]] = defaultdict(list)
    # Unfilled requests per relationship: the supplier owes them and ships them from its spare
    # capacity once it can; after the ramp-up they move to qualified alternatives.
    backorder: dict[str, float] = defaultdict(float)
    first_short: float | None = None  # first day a plant's output falls short
    first_supply_short: float | None = None  # first day a supplier ships less than asked
    out = Outcome()
    finished = sorted(k for k in producers if g.demand.get(k, 0.0) > 0)
    intermediate = {k for k in producers if k in feeding}

    last_day = 0
    for day in range(horizon):
        last_day = day
        # 1. suppliers ship what is asked (normal volume plus what they owe), capacity and
        #    their own inputs permitting
        owed = False
        for s_node, c in supplier_pairs:
            edges = g.outbound.get((s_node, c), [])
            requests = {e.id: g.flow(e) + backorder[e.id] for e in edges}
            total = sum(requests.values())
            if total <= 0:
                continue
            can = g.capacity.get((s_node, c), 0.0) * factor(s_node, day)
            if (s_node, c) in intermediate:
                for comp, qty in g.bom.get(c, {}).items():
                    if (s_node, comp) in inv and qty > 0:
                        can = min(can, inv[(s_node, comp)] / qty)
            made = min(total, can)
            if (s_node, c) in intermediate:
                for comp, qty in g.bom.get(c, {}).items():
                    if (s_node, comp) in inv:
                        inv[(s_node, comp)] = max(0.0, inv[(s_node, comp)] - made * qty)
            for e in feeding[(s_node, c)]:
                shipped = made * requests[e.id] / total
                backorder[e.id] = requests[e.id] - shipped
                owed = owed or backorder[e.id] > 1e-9
                arrive = day + transit[e.id]
                d = by_node.get(s_node)
                if d and d.active(day):
                    arrive += round(d.extra_lead_time_d)
                if e.route:
                    hub = next((h for h in e.route if h in hubs_closed), None)
                    if hub and hubs_closed[hub].active(day):
                        arrive += round(pri.hub_reroute_d)
                pipeline[e.id][arrive] += shipped
        # 2. after the ramp-up, plants move what is owed to qualified alternatives with spare
        #    capacity (normal volume and their own backorders come first)
        if owed and first_supply_short is None:
            first_supply_short = float(day)
        if owed and first_supply_short is not None and day >= first_supply_short + ramp:
            for f, c in affected:
                edges = g.inbound[(f, c)]
                short = [e for e in edges if backorder[e.id] > 1e-9]
                if not short:
                    continue
                spare: dict[str, float] = {}
                for e in edges:
                    if e in short or factor(e.src, day) < 1:
                        continue
                    pending = sum(backorder[x.id] for x in g.outbound.get((e.src, c), []))
                    room = (
                        g.capacity.get((e.src, c), 0.0)
                        - g.production.get((e.src, c), 0.0)
                        - pending
                    )
                    if room > 1e-9:
                        spare[e.id] = room
                owe = sum(backorder[e.id] for e in short)
                moved = min(owe, sum(spare.values()))
                if moved <= 0:
                    continue
                for sid, room in spare.items():
                    backorder[sid] += moved * room / sum(spare.values())
                for e in short:
                    backorder[e.id] -= moved * backorder[e.id] / owe
        # 3. arrivals; sea cargo reaching a closed gateway waits there (also cargo already at
        #    sea when the closure began)
        wait = math.ceil(gateway_wait(day))
        for f, c in affected:
            for s in g.inbound[(f, c)]:
                qty = pipeline[s.id].pop(day, 0.0)
                if wait and g.gateway in s.route:
                    pipeline[s.id][day + wait] += qty
                else:
                    inv[(f, c)] += qty
        # 4. plants make finished goods
        any_short = False
        by_plant: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for f, p in finished:
            by_plant[f].append((f, p))
        for f, pairs in by_plant.items():
            want = {}
            for k in pairs:
                d_rate = g.demand[k]
                cap = d_rate * pri.surge * factor(f, day)
                want[k] = min(d_rate + backlog[k], cap)
            use: dict[str, float] = defaultdict(float)
            for (_, p), w in want.items():
                for c, qty in g.bom.get(p, {}).items():
                    if (f, c) in inv:
                        use[c] += w * qty
            ratio = {c: min(1.0, inv[(f, c)] / u) if u > 0 else 1.0 for c, u in use.items()}
            for k, w in want.items():
                comps = [c for c in g.bom.get(k[1], {}) if c in ratio]
                made = w * min((ratio[c] for c in comps), default=1.0)
                for c in comps:
                    inv[(f, c)] = max(0.0, inv[(f, c)] - made * g.bom[k[1]][c])
                backlog[k] = max(0.0, backlog[k] + g.demand[k] - made)
                backlog_series[k].append(backlog[k])
                if backlog[k] > 1e-6:
                    any_short = True
        if any_short and first_short is None:
            first_short = float(day)
        value = sum(backlog[k] * g.products[k[1]].unit_value_usd for k in finished)
        out.timeline.append(
            {
                "day": day,
                "shortfall_value_usd": round(value, 2),
                "plants_short": sum(
                    1 for pairs in by_plant.values() if any(backlog[k] > 1e-6 for k in pairs)
                ),
                "gateway_wait_d": round(gateway_wait(day), 2),
            }
        )
        if any_short:
            out.recovery_d = None
        elif first_short is not None and out.recovery_d is None and day > end_all:
            out.recovery_d = float(day)
        if day > settle and not any_short and not owed:
            break

    # 5. orders
    start = g.as_of.date()
    for o in g.orders:
        k = (o.facility, o.product)
        ready = (o.due - start).days - o.export_lead_d
        delay = 0.0
        cause = "inputs"
        if k in producers and ready >= 0:
            series = backlog_series.get(k, [])
            idx = min(int(ready), len(series) - 1) if series else -1
            backlog_d = series[idx] if idx >= 0 and ready <= last_day else 0.0
            delay = backlog_d / g.demand[k] if g.demand.get(k) else 0.0
            if o.facility in hit:
                cause = "plant"
        crossing = ready + 2 + delay  # inland haul and gate-in before the vessel
        port_wait = gateway_wait(crossing) if crossing >= 0 else 0.0
        if port_wait > 0 and port_wait >= delay:
            cause = "gateway"
        delay += port_wait
        if delay <= 1e-6:
            continue
        out.impacts.append(
            OrderImpact(
                order_id=o.id,
                reference=o.reference,
                buyer=o.buyer,
                product=o.product,
                facility=o.facility,
                due=o.due.isoformat(),
                revenue_usd=o.revenue_usd,
                delay_d=round(delay, 1),
                late=delay > pri.order_slack_d,
                cause=cause,
            )
        )
    firsts = [x for x in (first_short, gateway.start_d if gateway else None) if x is not None]
    out.first_impact_d = min(firsts) if firsts else None
    if (
        gateway is not None
        and out.recovery_d is None
        and not any(t["plants_short"] for t in out.timeline[-1:])
    ):
        out.recovery_d = gateway.start_d + lost + clearing
    out.impacts.sort(key=lambda i: (-i.delay_d, i.due))
    return out


def monte_carlo(
    g: SupplyGraph, disruptions: list[Disruption], runs: int, seed: int
) -> list[Outcome]:
    rng = random.Random(seed)
    return [simulate(g, disruptions, Noise.draw(rng, disruptions)) for _ in range(runs)]
