"""Synthetic world v0: deterministic, labelled, fictional, and shaped for the golden path."""

from __future__ import annotations

from collections import defaultdict

import pytest
from cportal_core.enums import DataMode
from cportal_core.schemas.records import (
    BatchRecord,
    FacilityRecord,
    OrganizationRecord,
    SupplyEdgeRecord,
    TransportEventRecord,
)
from cportal_sim.world import HERO_FACTORY, World, build_world


@pytest.fixture(scope="module")
def world() -> World:
    return build_world()


def test_world_is_deterministic(world: World) -> None:
    again = build_world()
    assert [r.id for r in again.records] == [r.id for r in world.records]
    other = build_world("other_scenario")
    assert not {r.id for r in other.records} & {r.id for r in world.records}


def test_every_row_is_labelled_synthetic(world: World) -> None:
    for r in world.records:
        assert r.is_synthetic and r.data_mode == DataMode.SYNTHETIC
        assert r.scenario_id == world.scenario_id
        assert r.generator_version


def test_organizations_are_fictional_and_named_from_the_pack(world: World) -> None:
    orgs = [r for r in world.records if isinstance(r, OrganizationRecord)]
    assert orgs and all(o.is_fictional for o in orgs)
    assert all(o.name_key and o.name != o.name_key for o in orgs)  # a pack name, not the key


def test_supply_shares_sum_to_one(world: World) -> None:
    totals: dict[tuple[object, object], float] = defaultdict(float)
    for e in (r for r in world.records if isinstance(r, SupplyEdgeRecord)):
        totals[(e.to_facility_id, e.product_id)] += e.share
    assert totals and all(abs(t - 1) < 0.011 for t in totals.values())


def test_golden_path_structure(world: World) -> None:
    """Denim concentrated on Mill X; Factory A imports knit fabric through Chattogram."""
    by_id = {f.id: k for k, f in world.facilities.items()}
    denim = world.products["G-DENIM_FABRIC"].id
    knit = world.products["G-KNIT_FABRIC"].id
    edges = [r for r in world.records if isinstance(r, SupplyEdgeRecord)]
    mill_x = [
        e
        for e in edges
        if e.product_id == denim and by_id[e.from_facility_id].startswith("fabric_mill_3.")
    ]
    factories = {e.to_facility_id for e in edges if e.product_id == denim}
    assert len(mill_x) == len(factories) and all(e.share >= 0.7 for e in mill_x)
    hero = world.facilities[HERO_FACTORY].id
    imported = [
        e
        for e in edges
        if e.to_facility_id == hero
        and e.product_id == knit
        and by_id[e.from_facility_id].startswith("overseas_")
    ]
    assert imported and imported[0].mode == "sea"


def test_facilities_sit_at_real_clusters(world: World) -> None:
    facilities = [r for r in world.records if isinstance(r, FacilityRecord)]
    assert {f.cluster for f in facilities} >= {"gazipur", "cepz", "narayanganj", "dhaka_epz"}


def test_batches_follow_aql_25(world: World) -> None:
    batches = [r for r in world.records if isinstance(r, BatchRecord)]
    assert batches
    for b in batches:
        result = b.aql_result
        decision = "accept" if result["defects_found"] <= result["accept"] else "reject"
        assert result["decision"] == decision
        assert (b.status == "released") == (decision == "accept")


def test_actual_events_are_never_in_the_future(world: World) -> None:
    for e in (r for r in world.records if isinstance(r, TransportEventRecord)):
        if e.classifier == "ACT":
            assert e.event_ts < world.start
