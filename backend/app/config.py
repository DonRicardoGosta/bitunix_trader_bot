"""Alkalmazás konfiguráció / Application configuration.

A környezeti változókat Pydantic settings olvassa be. A teljes lista
a projekt gyökerében lévő ``.env.example``-ben dokumentált.
"""

from __future__ import annotations

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

    backend_cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    bitunix_api_key: str = ""
    bitunix_api_secret: str = ""
    bitunix_rest_base_url: str = "https://fapi.bitunix.com"
    bitunix_ws_public_url: str = "wss://fapi.bitunix.com/public/"
    bitunix_ws_private_url: str = "wss://fapi.bitunix.com/private/"
    bitunix_live_trading: bool = False
    bitunix_margin_coin: str = "USDT"

    # -- stratégia / scheduler ----------------------------------------------
    strategy_runner_enabled: bool = False
    strategy_interval_seconds: int = 300
    strategy_top_movers_enabled: bool = True
    strategy_top_movers_count: int = 3
    strategy_top_movers_cooldown_minutes: int = 240
    strategy_top_movers_direction_mode: Literal[
        "trend", "momentum_breakout", "mean_revert"
    ] = "momentum_breakout"
    strategy_top_movers_range_threshold: str = "0.66"
    strategy_min_margin_usdt: str = "0.25"
    strategy_margin_pct_of_balance: str = "0.01"

    # -- TP / SL beállítások (ROI százalékban a margin-on, leverage-vel együtt) --
    # 200 / 100 a userspec; a kockázat-kommentet lásd a tpsl.py-ban.
    strategy_tp_roi_pct: str = "200"
    strategy_sl_roi_pct: str = "100"
    strategy_tpsl_stop_type: Literal["MARK_PRICE", "LAST_PRICE"] = "MARK_PRICE"

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        """Vesszővel elválasztott CORS lista konvertálása listává."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cache-elt singleton settings instance."""
    return Settings()
