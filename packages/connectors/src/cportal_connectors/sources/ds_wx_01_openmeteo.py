"""DS-WX-01 · Open-Meteo: weather forecast, archive and marine (waves, currents, tides)."""

from __future__ import annotations

from functools import partial
from typing import Any

from cportal_core.areas import bbox
from cportal_core.enums import WeatherKind
from cportal_core.schemas.records import WeatherObservationRecord

from cportal_connectors.base import Connector, FieldNote, ProbeCall
from cportal_connectors.harness import ProbeContext
from cportal_connectors.parsers.hazards import parse_open_meteo

FORECAST = "https://api.open-meteo.com/v1/forecast"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
MARINE = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_VARS = (
    "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,wind_direction_10m,pressure_msl"
)
MARINE_VARS = (
    "wave_height,wind_wave_height,swell_wave_height,wave_period,wave_direction,"
    "ocean_current_velocity,ocean_current_direction,sea_level_height_msl"
)
REMAL = ("2024-05-24", "2024-05-29")  # Cyclone Remal landfall 26 May 2024 (backtest window)


def _point(name: str) -> dict[str, float]:
    lon, lat = bbox(name).center()
    return {"latitude": round(lat, 4), "longitude": round(lon, 4)}


class OpenMeteo(Connector):
    ds_id = "DS-WX-01"
    title = "Open-Meteo forecast, archive and marine APIs"
    parsers = {
        "forecast_port.json": partial(
            parse_open_meteo, point_name="ctg_port", kind=WeatherKind.FORECAST
        ),
        "marine_anchorage.json": partial(
            parse_open_meteo, point_name="ctg_anchorage", kind=WeatherKind.MARINE_FORECAST
        ),
        "archive_remal.json": partial(
            parse_open_meteo, point_name="ctg_port", kind=WeatherKind.ARCHIVE
        ),
        "marine_history_remal.json": partial(
            parse_open_meteo, point_name="ctg_anchorage", kind=WeatherKind.MARINE_ARCHIVE
        ),
    }
    record_types = (WeatherObservationRecord,)
    field_notes = {
        "marine_anchorage:hourly.sea_level_height_msl": FieldNote(
            "m vs global MSL", "Tides + inverted barometer + steric (MeteoFrance SMOC); not LAT"
        ),
        "marine_anchorage:hourly.wave_height": FieldNote("m", "Significant wave height"),
        "marine_anchorage:hourly.ocean_current_velocity": FieldNote("km/h", "Surface current"),
        "forecast_port:hourly.wind_gusts_10m": FieldNote("km/h", "Gusts at 10 m"),
        "forecast_port:hourly.precipitation": FieldNote("mm", "Hourly precipitation sum"),
        "forecast_port:hourly.pressure_msl": FieldNote("hPa", "Mean sea-level pressure"),
    }

    def probe(self, ctx: ProbeContext) -> None:
        port = _point("ctg_port_river")
        anchorage = _point("ctg_outer_anchorage")
        common = {"timezone": "UTC"}
        ctx.http(
            ProbeCall(
                "forecast_port",
                FORECAST,
                sample=True,
                params={**port, **common, "hourly": WEATHER_VARS, "forecast_days": 16},
            )
        )
        marine = ctx.http(
            ProbeCall(
                "marine_anchorage",
                MARINE,
                sample=True,
                params={
                    **anchorage,
                    **common,
                    "hourly": MARINE_VARS,
                    "forecast_days": 8,
                    "past_days": 2,
                },
            )
        )
        river = ctx.http(
            ProbeCall(
                "marine_river_berths",
                MARINE,
                params={**port, **common, "hourly": MARINE_VARS, "forecast_days": 1},
                note="Karnaphuli berths: does the marine grid cover the river?",
            )
        )
        ctx.http(
            ProbeCall(
                "archive_remal",
                ARCHIVE,
                sample=True,
                params={
                    **port,
                    **common,
                    "hourly": WEATHER_VARS,
                    "start_date": REMAL[0],
                    "end_date": REMAL[1],
                },
                note="Cyclone Remal window, ERA5-based archive",
            )
        )
        ctx.http(
            ProbeCall(
                "marine_history_remal",
                MARINE,
                sample=True,
                params={
                    **anchorage,
                    **common,
                    "hourly": MARINE_VARS,
                    "start_date": REMAL[0],
                    "end_date": REMAL[1],
                },
                note="historical marine via the same endpoint",
            )
        )
        ctx.http(
            ProbeCall(
                "bad_variable", FORECAST, "bad_param", params={**port, "hourly": "not_a_variable"}
            )
        )
        ctx.http(
            ProbeCall(
                "forecast_too_long",
                FORECAST,
                "oversized",
                params={**port, "hourly": "temperature_2m", "forecast_days": 30},
            )
        )
        ctx.http(
            ProbeCall(
                "marine_too_long",
                MARINE,
                "oversized",
                params={**anchorage, "hourly": "wave_height", "forecast_days": 16},
                note="docs give 0-8 days for marine forecast_days",
            )
        )
        ctx.http(
            ProbeCall(
                "client_timeout",
                FORECAST,
                "timeout",
                timeout_s=0.001,
                params={**port, "hourly": "temperature_2m"},
            )
        )
        for name, result in (("marine_anchorage", marine), ("marine_river_berths", river)):
            if isinstance(result.parsed, dict):
                ctx.metric(f"{name}_null_share", self._null_share(result.parsed))
                ctx.metric(
                    f"{name}_grid_point",
                    {k: result.parsed.get(k) for k in ("latitude", "longitude", "elevation")},
                )

    @staticmethod
    def _null_share(doc: dict[str, Any]) -> dict[str, float]:
        hourly = doc.get("hourly", {})
        out = {}
        for key, values in hourly.items():
            if key == "time" or not isinstance(values, list) or not values:
                continue
            out[key] = round(sum(v is None for v in values) / len(values), 3)
        return out


CONNECTOR = OpenMeteo()
