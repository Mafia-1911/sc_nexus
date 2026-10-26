"""AIS replay for the Control Tower map (G2: "live map shows Chattogram vessels, live or
replay"). aisstream has no Bangladesh coverage, so the map replays the seeded scenario's port
DES: each tick renders aisstream frames for every vessel present at the replay clock and runs
them through the real AIS parser (ADR-010), then upserts `ais_position_latest`. Everything is
labelled synthetic with the scenario's id.

The replay clock loops over the last `window_h` hours of the scenario's history at `speed`×.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from cportal_connectors.ais_synthetic import Visit, _state, encode_position
from cportal_connectors.canonical import ParseContext, scenario_uuid
from cportal_connectors.parsers.maritime import parse_aisstream_jsonl
from cportal_core.db import session_scope
from cportal_core.enums import DataMode
from cportal_core.loader import upsert
from cportal_core.models import AisPositionLatest
from cportal_sim.port_des import simulate, to_twin_visit
from cportal_sim.scenarios import load_scenario
from sqlalchemy import delete, text

log = logging.getLogger(__name__)
GENERATOR = "cportal-worker/ais-replay/0.1.0"
STALE = timedelta(minutes=20)


@dataclass
class AisReplay:
    scenario: str
    speed: float = 30.0
    window_h: float = 48.0
    database_url: str | None = None
    started: datetime = field(default_factory=lambda: datetime.now(UTC))
    visits: list[Visit] = field(default_factory=list)
    window_start: datetime | None = None
    last_sim: datetime | None = None

    def load(self) -> None:
        """Re-run the scenario's DES (deterministic: same seed and closures as the seed)."""
        spec = load_scenario(self.scenario)
        start = spec.start - timedelta(days=spec.history_days)
        end = spec.start + timedelta(days=spec.projection_days)
        closures = [spec.cyclone["closure"]] if spec.cyclone else []
        result = simulate(start, end, seed=spec.seed, closures=closures)
        self.window_start = spec.start - timedelta(hours=self.window_h)
        self.visits = [
            to_twin_visit(v, result.priors, result.seed)
            for v in result.visits
            if v.depart > self.window_start and v.arrive - timedelta(hours=24) < spec.start
        ]
        log.info("ais replay loaded", extra={"scenario": self.scenario, "visits": len(self.visits)})

    def sim_time(self, now: datetime | None = None) -> datetime:
        assert self.window_start is not None
        elapsed = ((now or datetime.now(UTC)) - self.started).total_seconds() * self.speed
        offset = elapsed % (self.window_h * 3600)
        return self.window_start + timedelta(seconds=offset)

    def frames(self, at: datetime) -> bytes:
        lines = []
        for visit in self.visits:
            state = _state(visit, at)
            if state is None:
                continue
            (lat, lon), knots, heading, status = state
            rng = random.Random(f"{visit.index}:{at.isoformat()}")
            frame = encode_position(visit.vessel, at, lat, lon, knots, heading, status, rng)
            lines.append(
                json.dumps(
                    {
                        "received_at": (at + timedelta(seconds=1)).isoformat(),
                        "frame": json.dumps(frame),
                        "is_synthetic": True,
                        "scenario_id": self.scenario,
                        "generator": GENERATOR,
                    }
                )
            )
        return "\n".join(lines).encode()

    def tick(self) -> int:
        """Advance the replay clock and write the positions it implies. Returns rows written."""
        if self.window_start is None:
            self.load()
        at = self.sim_time()
        scenario_id = scenario_uuid(self.scenario)
        ctx = ParseContext(
            "DS-AIS-01",
            DataMode.SYNTHETIC,
            fetched_at=at,
            scenario_id=scenario_id,
            generator_version=GENERATOR,
        )
        records = parse_aisstream_jsonl(self.frames(at), ctx)
        with session_scope(self.database_url) as session:
            # First tick or loop restart: clear the scenario's positions, which otherwise only
            # move forward (seeded positions are newer than the replay clock).
            wrapped = self.last_sim is None or at < self.last_sim
            positions = AisPositionLatest
            if wrapped:  # the loop restarted: positions only move forward otherwise
                session.execute(delete(positions).where(positions.scenario_id == scenario_id))
            counts = upsert(session, records)
            session.execute(
                delete(positions).where(
                    positions.scenario_id == scenario_id, positions.ts < at - STALE
                )
            )
            session.execute(
                text("SELECT pg_notify('positions', :payload)"),
                {"payload": json.dumps({"scenario": self.scenario, "ts": at.isoformat()})},
            )
        self.last_sim = at
        return counts.get("ais_position_latest", 0)
