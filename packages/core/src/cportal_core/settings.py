"""Runtime settings from the environment and `.env` (02-architecture.md §13).

Secrets are `SecretStr` so they never print. `.env.example` documents every variable and the
source card that needs it. Each credential has a canonical name (its field name, upper-cased)
plus accepted aliases, and `.env` is read leniently: `"NAME"="value"` works like NAME=value.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import AliasChoices, Field, SecretStr
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from cportal_core import __version__
from cportal_core.paths import repo_root


def _credential(*aliases: str) -> Any:
    """An optional secret readable by its canonical name or any alias."""
    return Field(default=None, validation_alias=AliasChoices(*aliases))


def _names(field_name: str, info: FieldInfo) -> list[str]:
    names = [field_name.upper()]
    alias = info.validation_alias
    if isinstance(alias, AliasChoices):
        names += [str(choice).upper() for choice in alias.choices]
    elif isinstance(alias, str):
        names.append(alias.upper())
    return names


class LenientDotEnv(PydanticBaseSettingsSource):
    """Reads `.env` with python-dotenv, but strips quotes around names and matches aliases."""

    def __init__(self, settings_cls: type[BaseSettings], path: Path) -> None:
        super().__init__(settings_cls)
        self.path = path

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False  # unused: __call__ resolves every field at once

    def __call__(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        raw = {
            key.strip().strip("\"'").upper(): value
            for key, value in dotenv_values(self.path).items()
            if value
        }
        found: dict[str, Any] = {}
        for name, info in self.settings_cls.model_fields.items():
            for candidate in _names(name, info):
                if candidate in raw:
                    found[name] = raw[candidate]
                    break
        return found


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", validate_by_name=True, validate_by_alias=True)

    cportal_env: str = "dev"
    # Optional contact (URL or e-mail) for the User-Agent; Nominatim and Overpass ask for one.
    cportal_contact: str = ""
    # Q-07: the product name is a variable; the repo codename stays "Cportal".
    brand_name: str = Field(
        default="ShipperFast", validation_alias=AliasChoices("CPORTAL_BRAND_NAME")
    )
    # Q-05: which display names the synthetic world uses (config/name_packs/<pack>.yaml).
    name_pack: str = Field(default="fictional", validation_alias=AliasChoices("CPORTAL_NAME_PACK"))

    database_url: str = Field(
        default="postgresql+psycopg://cportal:cportal@localhost:5432/cportal",
        validation_alias=AliasChoices("DATABASE_URL"),
    )
    # Q-03: local LLM only (ADR-008). Any OpenAI-compatible local server works (Ollama default).
    llm_base_url: str = Field(
        default="http://localhost:11434/v1", validation_alias=AliasChoices("LLM_BASE_URL")
    )
    llm_model: str = Field(default="qwen3:4b", validation_alias=AliasChoices("LLM_MODEL"))

    # Source credentials, by DS-ID. Empty means "not provided yet": the probe records it under
    # "needs you" and moves on.
    aisstream_api_key: SecretStr | None = _credential(  # DS-AIS-01
        "AISSTREAM_API_KEY", "AIS_STREAM_APIKEY", "AIS_STREAM_API_KEY"
    )
    gfw_api_token: SecretStr | None = _credential(  # DS-AIS-02, DS-SAT-04
        "GFW_API_TOKEN", "GLOBAL_FISHING_WATCH_GFW_ACCESS_TOKEN", "GFW_ACCESS_TOKEN"
    )
    openfda_api_key: SecretStr | None = _credential(  # DS-PHARMA-01 (optional)
        "OPENFDA_API_KEY", "OPEN_FDA_APIKEY", "OPEN_FDA_API_KEY"
    )
    comtrade_api_key: SecretStr | None = _credential(  # DS-TRADE-01
        "COMTRADE_API_KEY", "UN_COMTRADE_APIKEY", "UN_COMTRADE_API_KEY"
    )
    roboflow_api_key: SecretStr | None = _credential(  # DS-VIS-04, DS-VIS-05
        "ROBOFLOW_API_KEY", "ROBOFLOW_APIKEY"
    )
    earthdata_token: SecretStr | None = _credential(  # DS-SAT-05 (proposed)
        "EARTHDATA_TOKEN", "NASA_EARTHDATA_TOKEN"
    )
    firms_map_key: SecretStr | None = _credential(  # DS-WX-05 (proposed)
        "FIRMS_MAP_KEY", "NASA_FIRMS_MAPKEY", "NASA_FIRMS_MAP_KEY"
    )
    # DS-GEO-03: HeiGIT runs openrouteservice, so its dashboard calls the ORS key a HeiGIT key.
    ors_api_key: SecretStr | None = _credential("ORS_API_KEY", "HEIGIT_KEY", "HEIGIT_API_KEY")
    kaggle_api_token: SecretStr | None = _credential(  # DS-VIS-01 mirror, DS-SUP-03
        "KAGGLE_API_TOKEN", "KAGGLE_APIKEY"
    )
    # DS-NEWS-04: a pre-approved identifier. Kept secret anyway: quotas are per appname and
    # ReliefWeb echoes it in every response's links.
    reliefweb_appname: SecretStr | None = _credential("RELIEFWEB_APPNAME")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Real environment variables win over .env, as usual.
        return (
            init_settings,
            env_settings,
            LenientDotEnv(settings_cls, repo_root() / ".env"),
            file_secret_settings,
        )

    def secret(self, env_name: str) -> str | None:
        """Value of a credential by its canonical env var name, or None when unset or blank."""
        value = getattr(self, env_name.lower(), None)
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        return value or None

    def secret_values(self) -> list[str]:
        """Every non-empty secret, for redacting anything written to disk or logs."""
        out = []
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, SecretStr) and value.get_secret_value():
                out.append(value.get_secret_value())
        return out

    def user_agent(self) -> str:
        contact = f"; +{self.cportal_contact}" if self.cportal_contact else ""
        return f"Cportal/{__version__} ({self.brand_name} research prototype{contact})"


@cache
def get_settings() -> Settings:
    return Settings()
