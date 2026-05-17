"""Alkalmazás konfiguráció / Application configuration.

A környezeti változókat Pydantic settings olvassa be. A teljes lista
a projekt gyökerében lévő ``.env.example``-ben dokumentált.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Globális futási konfiguráció."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    secret_key: str = "dev-secret-change-me"

    database_url: str = (
        "postgresql+asyncpg://trader:trader@localhost:5432/bitunix_trader"
    )

    # Tárolás stringként: a pydantic-settings a list[str] mezőket JSON-ként próbálná
    # dekódolni a környezetből (Alembic / Docker), ami vesszős listánál hibát okoz.
    # Elfogadunk CSV-t, JSON tömböt (stringként), vagy Python listát (tesztek).
    backend_cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000"
    )

    bitunix_api_key: str = ""
    bitunix_api_secret: str = ""
    bitunix_rest_base_url: str = "https://fapi.bitunix.com"
    bitunix_ws_public_url: str = "wss://fapi.bitunix.com/public/"
    bitunix_ws_private_url: str = "wss://fapi.bitunix.com/private/"
    bitunix_margin_coin: str = "USDT"

    # -- stratégia scheduler (infra; algoritmus paraméterek → DB, lásd strategy_runtime_config) --
    strategy_runner_enabled: bool = True
    strategy_interval_seconds: int = 30

    # -- TP/SL automatikus belövő / calibration --
    calibration_enabled: bool = True
    calibration_interval_seconds: int = 3600  # 1 óra
    calibration_lookback_minutes: int = 120  # 2 óra
    calibration_top_n: int = 20
    calibration_kline_interval: str = "1m"
    calibration_tp_atr_mult: str = "3.0"
    calibration_sl_atr_mult: str = "1.5"
    # A trading akkor "engedélyezett", ha a legutóbbi SIKERES kalibráció
    # fiatalabb mint ez (vagy az interval × 2, amelyik nagyobb).
    calibration_max_age_minutes: int = 180
    # Ha True, a tradelés (manuális is) blokkolva van amíg nincs friss kalibráció.
    require_calibration_for_trading: bool = True

    # TP/SL position attach: várakozás a fill + pending positions API között
    position_tpsl_resolve_max_attempts: int = Field(default=40, ge=5, le=120)
    position_tpsl_resolve_delay_seconds: float = Field(default=0.5, ge=0.1, le=5.0)

    # -- élő UI push (WebSocket invalidáció + opcionális tick) ----------------
    live_ui_push_enabled: bool = True
    live_ui_push_interval_seconds: float = Field(
        default=2.0,
        ge=0.0,
        le=120.0,
        description=(
            "Ha van websocket kliens, ennyi másodpercenként invalidációs push. "
            "0: nincs időzített tick (csak eseményvezérelt push)."
        ),
    )

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def _normalize_cors_csv(cls, value: object) -> str:
        """CORS originek egyetlen CSV stringgé (vesszővel), alapértelmezéssel."""
        if value is None:
            return "http://localhost:3000,http://127.0.0.1:3000"
        if isinstance(value, list):
            parts = [str(x).strip() for x in value if str(x).strip()]
            return (
                ",".join(parts)
                if parts
                else "http://localhost:3000,http://127.0.0.1:3000"
            )
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return "http://localhost:3000,http://127.0.0.1:3000"
            if s.startswith("["):
                try:
                    parsed = json.loads(s)
                except json.JSONDecodeError:
                    return s
                if isinstance(parsed, list):
                    parts = [str(x).strip() for x in parsed if str(x).strip()]
                    return (
                        ",".join(parts)
                        if parts
                        else "http://localhost:3000,http://127.0.0.1:3000"
                    )
            parts = [p.strip() for p in s.split(",") if p.strip()]
            return (
                ",".join(parts)
                if parts
                else "http://localhost:3000,http://127.0.0.1:3000"
            )
        return "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cache-elt singleton settings instance."""
    return Settings()
