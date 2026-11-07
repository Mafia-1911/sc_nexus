# ruff: noqa: E501  (HTML fixtures copy the page structure verbatim)
"""DS-PORT-10 parsers on small copies of the CPA page structures (no network)."""

from __future__ import annotations

from datetime import UTC, datetime

from cportal_connectors import cpa_tos as c

PCS = """<table><tr><th>Visit Ref.</th><th>Vessel Name</th><th>Rotation</th><th>Phase</th><th>ETA</th>
<th>ATA</th><th>Berth</th><th>Operator</th><th>Agent</th><th>ETD</th><th>ATD</th></tr>
<tr><td>HSLKENSI202651101</td><td>HSL KENSINGTON</td><td>2026/5110</td><td>inbound</td>
<td>2026/11/03 10:00:00 am</td><td></td><td></td><td></td><td>SHOR</td><td>2026/11/10 10:00:00 pm</td><td></td></tr>
</table>"""

AT_BERTH = (
    """<table><tr><td>SlNo.</td><td>Berth</td><td>Vessel Name</td><td>Berthed On</td></tr>
<tr><td>1</td><td>NCT-5</td><td>BOX ENDEAVOUR</td><td>07/11/2026 09:36:00</td><td>08/11/2026 10:00:00</td>
<td>1d 0h 24m</td><td></td>"""
    + "".join(
        f"<td>{n}</td>"
        for n in (
            679,
            1063,
            496,
            799,
            183,
            264,
            135,
            259,
            1295,
            2093,
            0,
            0,
            0,
            0,
            135,
            259,
            1295,
            2093,
        )
    )
    + "</tr></table>"
)

YARD = """<table><tr><td>YARD</td><td>CAPACITY TUES</td></tr><tr><td>Tues</td><td>%</td></tr>
<tr><td>NCT</td><td>13876</td><td>28952</td><td>208.65%</td><td>-15076</td><td>-108.65%</td><td>17555</td></tr></table>"""

LYING = """<table><tr><td>LOCATION.</td><td>CONTAINER</td></tr><tr><td>BOX</td><td>TEUS</td></tr>
<tr><td>CPA</td><td>21,325</td><td>34,053</td></tr></table>"""

LAST24 = """<table><tr><td>Lying Container</td></tr><tr><td>Type</td><td>Quantity</td></tr>
<tr><td>FCL</td><td>37138</td><td>TEUs</td></tr></table>"""


def test_dhaka_times_become_utc_in_both_site_formats() -> None:
    assert c.dhaka_ts("2026/11/03 10:00:00 pm") == datetime(2026, 11, 3, 16, 0, tzinfo=UTC)
    assert c.dhaka_ts("07/11/2026 09:36:00") == datetime(2026, 11, 7, 3, 36, tzinfo=UTC)
    assert c.dhaka_ts("") is None and c.dhaka_ts("0000-00-00 00:00:00") is None


def test_keys_normalise_berths_and_vessel_names() -> None:
    assert c.berth_key("GCB07") == c.berth_key("GCB-7") == "GCB7"
    assert c.berth_key("CCT/1") == "CCT1"
    assert (
        c.vessel_key("MV. BETTER VICTORY")
        == c.vessel_key("M.V. Better Victory")
        == "BETTER VICTORY"
    )


def test_pcs_visits_parse_with_phase_and_times() -> None:
    [v] = c.parse_pcs(PCS)
    assert v["phase"] == "INBOUND" and v["agent"] == "SHOR" and v["ata"] is None
    assert v["eta"] == datetime(2026, 11, 3, 4, 0, tzinfo=UTC)


def test_at_berth_cargo_progress_adds_up() -> None:
    [r] = c.parse_at_berth(AT_BERTH)
    assert r["berth"] == "NCT-5" and r["berthed_on"] == datetime(2026, 11, 7, 3, 36, tzinfo=UTC)
    imp, exp = r["import"], r["export"]
    assert imp["discharged_box"] + imp["balance_box"] == imp["total_box"] == 679
    assert exp["total_teu"] == 259 + 2093 and exp["loaded_teu"] == 0 and exp["balance_teu"] == 2352


def test_yard_lying_and_last24_tables() -> None:
    [y] = c.parse_yard(YARD)
    assert y == {"yard": "NCT", "capacity_teu": 13876, "used_teu": 28952, "used_pct": 208.65,
                 "free_teu": -15076, "boxes": 17555}  # fmt: skip
    assert c.parse_lying(LYING) == [{"location": "CPA", "boxes": 21325, "teu": 34053}]
    assert c.parse_quantities(LAST24) == {"Lying Container": {"FCL": 37138.0}}
