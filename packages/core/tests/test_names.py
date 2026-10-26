"""Name packs (Q-05) and the adverse-attribute guardrail (AGENTS.md rule 3)."""

from __future__ import annotations

from cportal_core.names import display_name, load_pack


def test_fictional_pack_is_the_default_and_has_no_real_names() -> None:
    pack = load_pack("fictional")
    assert pack.names["garment_exporter_1"] and not pack.has_real_names


def test_bd_demo_shows_real_names_only_in_neutral_views() -> None:
    pack = load_pack("bd_demo")
    real = display_name("garment_exporter_2", "x", pack=pack)
    fictional = load_pack("fictional").names["garment_exporter_2"]
    assert real != fictional  # a real, cited name in neutral views
    assert display_name("garment_exporter_2", "x", adverse=True, pack=pack) == fictional
    # Keys without a real name fall back to the fictional pack the bd_demo pack extends.
    assert (
        display_name("fabric_mill_3", "x", pack=pack)
        == load_pack("fictional").names["fabric_mill_3"]
    )
    assert display_name("no_such_key", "fallback", pack=pack) == "fallback"


def test_every_real_name_cites_a_source() -> None:
    pack = load_pack("bd_demo")
    assert pack.real_keys and pack.real_keys <= set(pack.sources)
    assert all(pack.sources[k].startswith("https://") for k in pack.real_keys)
    assert pack.banner and not pack.allow_adverse
