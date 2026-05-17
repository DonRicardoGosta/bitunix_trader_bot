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
    bitunix_live_trading: bool = False
    bitunix_margin_coin: str = "USDT"

    # -- stratégia / scheduler ----------------------------------------------
    # Alapból be: induláskor elindul a háttér-futó; tesztekben kapcsold ki env-vel.
    strategy_runner_enabled: bool = True
    strategy_interval_seconds: int = 30
    # Tickerrangsor max. mélysége (top signal entries).
    strategy_scan_limit_max: int = 1000
    # Top signal entries: top abs 24h movers + kline megerősítés (long/short).
    strategy_top_signal_entries_enabled: bool = True
    strategy_top_signal_entries_count: int = 2
    strategy_top_signal_entries_scan_limit: int = 1000
    strategy_top_signal_entries_kline_lookahead: int = 40
    strategy_top_signal_entries_kline_interval: str = "15m"
    strategy_top_signal_entries_kline_limit: int = 80
    strategy_top_signal_entries_cooldown_minutes: int = 240
    strategy_top_signal_entries_min_abs_change_pct: str = "1.0"
    strategy_top_signal_entries_range_threshold: str = "0.60"
    strategy_top_signal_entries_max_kline_concurrency: int = 10
    # WF variációs coin-elemzés (48h lookback) szűrő + TP/SL a javasolt konfigból.
    strategy_top_signal_entries_wf_gate_enabled: bool = False
    strategy_top_signal_entries_wf_lookback_minutes: int = 2880
    strategy_top_signal_entries_wf_cooldown_minutes: int = 60
    strategy_top_signal_entries_wf_choppiness_max: str = "1.72"
    strategy_min_margin_usdt: str = "0.25"
    strategy_margin_pct_of_balance: str = "0.01"

    # -- TP / SL beállítások (ROI százalékban a margin-on, leverage-vel együtt) --
    # 200 / 100 a userspec; a kockázat-kommentet lásd a tpsl.py-ban.
    # Csak fallback-ként, ha a kalibráció ``lookup``-ja nem ad move %%-et.
    strategy_tp_roi_pct: str = "200"
    strategy_sl_roi_pct: str = "100"
    # 0 = kikapcsolva. >0: stratégiák kihagyják a belépést, ha a számolt TP
    # margin-ROI célja (tp_move_pct × leverage) ennél kisebb lenne.
    strategy_min_tp_roi_pct: str = "0"
    strategy_tpsl_stop_type: Literal["MARK_PRICE", "LAST_PRICE"] = "MARK_PRICE"

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
