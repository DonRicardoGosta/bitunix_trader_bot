"""Teszt segéd: StrategyContext top_signal_entries konfiggal."""

from __future__ import annotations

from app.bitunix.client import BitunixClient
from app.config import Settings, get_settings
from app.schemas.strategy_config import TopSignalEntriesConfig
from app.services.strategy.base import StrategyContext
from app.services.strategy_runtime_config import DEFAULT_TOP_SIGNAL_ENTRIES_CONFIG
from sqlalchemy.ext.asyncio import AsyncSession


def make_strategy_context(
    session: AsyncSession,
    client: BitunixClient,
    *,
    settings: Settings | None = None,
    config: TopSignalEntriesConfig | None = None,
    triggered_by: str = "scheduler",
    **config_overrides: object,
) -> StrategyContext:
    cfg = config or DEFAULT_TOP_SIGNAL_ENTRIES_CONFIG
    if config_overrides:
        cfg = cfg.model_copy(update=config_overrides)  # type: ignore[arg-type]
    return StrategyContext(
        session=session,
        client=client,
        settings=settings or get_settings(),
        top_signal_entries=cfg,
        triggered_by=triggered_by,
    )
