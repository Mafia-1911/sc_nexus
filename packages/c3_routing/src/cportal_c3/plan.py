"""Plans (C3 §5–6): candidate mode chains, Monte Carlo time, cost, CO2e, Pareto, departures.

Candidates: three road routes (fastest, shortest, a detour around the fastest), and from
Chattogram also road + rail via Kamalapur ICD and road + barge via Pangaon. Each chain is
simulated: transfer dwell, waits for the next running service (some are cancelled), run times
and road time by departure hour, all lognormal. The non-dominated set on (P50 time, cost, CO2e)
is returned with on-time probabilities and a departure-window sweep.
"""

from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from cportal_core.timeutil import DHAKA

from cportal_c3.network import RoadNet, Traversal
from cportal_c3.priors import Priors

Z90 = 1.2816


def lognormal(rng: random.Random, p50: float, p90: float) -> float:
    if p50 <= 0:
        return 0.0
    sigma = max(1e-6, math.log(max(p90, p50 * 1.0001) / p50) / Z90)
    return p50 * math.exp(rng.gauss(0.0, sigma))


@dataclass
class Leg:
    mode: str  # road | rail | barge | transfer
    origin: str
    dest: str
    km: float = 0.0
    hours_by_start: list[float] = field(default_factory=list)  # road: hours for each start hour
    ban_wait_h: float = 0.0
    coords: list[tuple[float, float]] = field(default_factory=list)
    service: dict[str, Any] | None = None
    dwell: tuple[float, float] | None = None
    cost_bdt: float = 0.0
    co2e_kg: float = 0.0
    factor: dict[str, Any] | None = None
    note: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "from": self.origin,
            "to": self.dest,
            "km": round(self.km, 1),
            "cost_bdt": round(self.cost_bdt),
            "co2e_kg": round(self.co2e_kg, 1),
            "factor": self.factor,
            "note": self.note,
        }


@dataclass
class Plan:
    name: str
    legs: list[Leg]
    samples: list[float] = field(default_factory=list)  # hours from departure
    on_time_prob: float | None = None
    pareto_rank: int = 0
    departures: list[dict[str, Any]] = field(default_factory=list)
    explanation: str = ""

    @property
    def modes(self) -> list[str]:
        return [leg.mode for leg in self.legs if leg.mode != "transfer"]

    @property
    def km(self) -> float:
        return sum(leg.km for leg in self.legs)

    @property
    def cost_bdt(self) -> float:
        return sum(leg.cost_bdt for leg in self.legs)

    @property
    def co2e_kg(self) -> float:
        return sum(leg.co2e_kg for leg in self.legs)

    def quantile(self, q: float) -> float:
        s = sorted(self.samples)
        return s[min(len(s) - 1, int(q * len(s)))] if s else math.inf


@dataclass(frozen=True)
class Request:
    origin: str
    dest: str
    depart: datetime
    deadline: datetime | None = None
    qty_teu: int = 1
    reefer: bool = False
    max_transit_h: float | None = None


class Planner:
    def __init__(self, net: RoadNet, priors: Priors, factors: dict[str, dict[str, Any]]) -> None:
        self.net = net
        self.p = priors
        self.factors = factors  # key (road|reefer|rail|barge) → {id, value (kg/tkm), label, year}
        self._roads: dict[tuple[str, str, str], tuple[list[int], list[float], Traversal]] = {}

    # --- legs ---------------------------------------------------------------------------

    def _node(self, place: str) -> int:
        spec = self.p.places[place]
        return self.net.nearest(float(spec["lat"]), float(spec["lon"]))

    def road_options(self, origin: str, dest: str, depart: datetime) -> list[tuple[str, list[int]]]:
        o, d = self._node(origin), self._node(dest)
        fastest = self.net.path(o, d, "seconds")
        shortest = self.net.path(o, d, "length_m")
        detour = self.net.path(o, d, "seconds", avoid=set(itertools.pairwise(fastest)))
        out: list[tuple[str, list[int]]] = [("fastest road", fastest)]
        for name, path in (("shortest road", shortest), ("alternative road", detour)):
            if all(_overlap(path, p) < 0.85 for _, p in out):
                out.append((name, path))
        return out

    def road_leg(
        self, origin: str, dest: str, path: list[int], depart: datetime, qty: int, reefer: bool
    ) -> Leg:
        # hours_by_start[h]: road time leaving at Dhaka hour h (ban and rush hours are local)
        midnight = depart.astimezone(DHAKA).replace(hour=0, minute=0, second=0, microsecond=0)
        runs = [self.net.traverse(path, midnight + timedelta(hours=h)) for h in range(24)]
        first = self.net.traverse(path, depart)
        road = self.p.road
        cost = max(float(road["min_bdt"]), first.km * float(road["bdt_per_km"])) * qty
        if reefer:
            cost *= float(road["reefer_uplift"])
        factor = self.factors["reefer" if reefer else "road"]
        return Leg(
            mode="road",
            origin=origin,
            dest=dest,
            km=first.km,
            hours_by_start=[r.hours for r in runs],
            ban_wait_h=first.ban_wait_h,
            coords=first.coords,
            cost_bdt=cost,
            co2e_kg=self._co2e(factor, first.km, qty),
            factor=_cite(factor),
            note=", ".join(
                f"{k} {v:.0f} km"
                for k, v in sorted(first.highways.items(), key=lambda kv: -kv[1])[:3]
            ),
        )

    def _co2e(self, factor: dict[str, Any], km: float, qty: int) -> float:
        tonnes = qty * float(self.p["cargo_t_per_teu"])
        return float(factor["value"]) * tonnes * km

    def transfer(self, place: str, qty: int) -> Leg:
        spec = self.p["transfers"][place]
        return Leg(
            mode="transfer",
            origin=place,
            dest=place,
            dwell=(float(spec["p50_h"]), float(spec["p90_h"])),
            cost_bdt=float(spec["bdt"]) * qty,
            note=str(spec["note"]),
        )

    def service_leg(self, key: str, qty: int) -> Leg:
        s = self.p["services"][key]
        fx = float(self.p["fx_bdt_per_usd"])
        per_teu = float(s.get("bdt_per_teu") or float(s.get("usd_per_teu", 0)) * fx)
        factor = self.factors[str(s["mode"])]
        start, end = self.p.places[s["origin"]], self.p.places[s["dest"]]
        return Leg(
            mode=str(s["mode"]),
            origin=str(s["origin"]),
            dest=str(s["dest"]),
            km=float(s["km"]),
            service={**s, "key": key},
            cost_bdt=per_teu * qty,
            co2e_kg=self._co2e(factor, float(s["km"]), qty),
            factor=_cite(factor),
            coords=[
                (float(start["lon"]), float(start["lat"])),
                (float(end["lon"]), float(end["lat"])),
            ],
            note=f"{len(s['departures_h'])} departure(s) a day"
            + (f" on weekdays {s['departures_weekdays']}" if "departures_weekdays" in s else "")
            + f", {s['cancel_prob']:.0%} cancelled (modelled)",
        )

    def candidates(self, req: Request) -> list[Plan]:
        plans: list[Plan] = []
        gate = [self.transfer(req.origin, req.qty_teu)] if req.origin in self.p["transfers"] else []
        for name, path in self.road_options(req.origin, req.dest, req.depart):
            legs = [
                *gate,
                self.road_leg(req.origin, req.dest, path, req.depart, req.qty_teu, req.reefer),
            ]
            plans.append(Plan(name, legs))
        if not req.reefer:  # rail and barge carry no reefer plugs in this model
            for key, s in self.p["services"].items():
                if s["origin"] != req.origin or s["dest"] == req.dest:
                    continue
                hub = str(s["dest"])
                tail = self.road_options(hub, req.dest, req.depart)[0][1]
                legs = [
                    *gate,
                    self.service_leg(key, req.qty_teu),
                    self.transfer(hub, req.qty_teu),
                    self.road_leg(hub, req.dest, tail, req.depart, req.qty_teu, False),
                ]
                plans.append(Plan(f"{s['mode']} via {self.p.places[hub]['name']}", legs))
        return plans

    # --- simulation ---------------------------------------------------------------------

    def simulate(self, plan: Plan, depart: datetime, n: int, seed: int) -> list[float]:
        rng = random.Random(seed)
        sigma = float(self.p.road["sigma"])
        out = []
        for _ in range(n):
            clock = depart
            for leg in plan.legs:
                if leg.mode == "transfer" and leg.dwell:
                    clock += timedelta(hours=lognormal(rng, *leg.dwell))
                elif leg.mode == "road":
                    base = leg.hours_by_start[clock.astimezone(DHAKA).hour]
                    clock += timedelta(hours=base * math.exp(rng.gauss(0.0, sigma)))
                elif leg.service is not None:
                    clock = _next_departure(leg.service, clock, rng)
                    s = leg.service
                    clock += timedelta(
                        hours=lognormal(rng, float(s["run_p50_h"]), float(s["run_p90_h"]))
                    )
            out.append((clock - depart).total_seconds() / 3600)
        return out

    def evaluate(self, req: Request, n: int | None = None, seed: int = 7) -> list[Plan]:
        n = n or int(self.p["monte_carlo"])
        plans = self.candidates(req)
        for plan in plans:
            plan.samples = self.simulate(plan, req.depart, n, seed)
            if req.deadline is not None:
                budget = (req.deadline - req.depart).total_seconds() / 3600
                plan.on_time_prob = round(
                    sum(t <= budget for t in plan.samples) / len(plan.samples), 3
                )
        feasible = [
            p for p in plans if req.max_transit_h is None or p.quantile(0.9) <= req.max_transit_h
        ] or plans
        for p in feasible:
            p.pareto_rank = sum(_dominates(q, p) for q in feasible if q is not p)
        feasible.sort(key=lambda p: (p.pareto_rank, p.quantile(0.5)))
        for p in feasible:
            p.explanation = self.explain(p, req)
        return feasible

    def sweep(self, plan: Plan, req: Request, seed: int = 11) -> list[dict[str, Any]]:
        """Departure window (C3 §6 L2): P90 hours and on-time probability every few hours."""
        cfg = self.p["departure_sweep"]
        out = []
        for k in range(0, int(cfg["hours"]) + 1, int(cfg["step_h"])):
            depart = req.depart + timedelta(hours=k)
            samples = sorted(self.simulate(plan, depart, 120, seed))
            row: dict[str, Any] = {
                "depart": depart.isoformat(),
                "p90_h": round(samples[int(0.9 * len(samples))], 1),
            }
            if req.deadline is not None:
                budget = (req.deadline - depart).total_seconds() / 3600
                row["on_time_prob"] = round(sum(t <= budget for t in samples) / len(samples), 3)
            out.append(row)
        return out

    def explain(self, plan: Plan, req: Request) -> str:
        """Why this plan: the dominant time and cost terms and any binding constraint."""
        terms: list[tuple[float, str]] = []
        for leg in plan.legs:
            if leg.mode == "transfer" and leg.dwell:
                terms.append(
                    (leg.dwell[0], f"{leg.note} at {leg.origin} (P50 {leg.dwell[0]:.0f} h)")
                )
            elif leg.mode == "road":
                h = leg.hours_by_start[req.depart.astimezone(DHAKA).hour]
                terms.append((h, f"{leg.km:.0f} km by road ({leg.note}), ≈ {h:.1f} h"))
            elif leg.service is not None:
                terms.append(
                    (
                        float(leg.service["run_p50_h"]),
                        f"{leg.mode} {leg.km:.0f} km, waits for the next running departure",
                    )
                )
        terms.sort(reverse=True)
        biggest_cost = max(plan.legs, key=lambda leg: leg.cost_bdt)
        parts = [f"Time is mostly {terms[0][1]}." if terms else ""]
        parts.append(
            f"Most of the cost is the {biggest_cost.mode} leg (Tk {biggest_cost.cost_bdt:,.0f})."
        )
        bans = sum(leg.ban_wait_h for leg in plan.legs)
        if bans > 0.05:
            parts.append(f"Waits {bans:.1f} h for the Dhaka truck ban to lift.")
        if plan.pareto_rank:
            parts.append(f"Dominated by {plan.pareto_rank} other plan(s): shown for comparison.")
        return " ".join(p for p in parts if p)


def _dominates(a: Plan, b: Plan) -> bool:
    av = (a.quantile(0.5), a.cost_bdt, a.co2e_kg)
    bv = (b.quantile(0.5), b.cost_bdt, b.co2e_kg)
    return all(x <= y for x, y in zip(av, bv, strict=True)) and av != bv


def _overlap(a: list[int], b: list[int]) -> float:
    sa, sb = set(itertools.pairwise(a)), set(itertools.pairwise(b))
    return len(sa & sb) / max(1, min(len(sa), len(sb)))


def _cite(factor: dict[str, Any]) -> dict[str, Any]:
    return {k: factor[k] for k in ("id", "label", "value", "year", "source") if k in factor}


def _next_departure(service: dict[str, Any], clock: datetime, rng: random.Random) -> datetime:
    """The next scheduled departure at or after `clock` that is not cancelled (Dhaka timetable)."""
    hours = sorted(int(h) for h in service["departures_h"])
    days = service.get("departures_weekdays")
    day = clock.astimezone(DHAKA).replace(minute=0, second=0, microsecond=0)
    for _ in range(24 * 21):
        if (
            (days is None or day.weekday() in days)
            and day.hour in hours
            and day >= clock - timedelta(minutes=1)
        ) and rng.random() >= float(service["cancel_prob"]):
            return day
        day += timedelta(hours=1)
    return day
