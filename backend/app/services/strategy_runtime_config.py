"""Stratégia paraméterek DB-ben (AppRuntimeSetting JSON), kód alapértelmezéssel."""

from __future__ import annotations

import json
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.strategy_config import TopSignalEntriesConfig, TopSignalEntriesConfigPatch
from app.services.runtime_settings import get_runtime_raw, set_runtime_json_value

TOP_SIGNAL_ENTRIES_CONFIG_KEY = "strategy.top_signal_entries.config"

# Alapértelmezés, ha még nincs DB rekord (nem env).
DEFAULT_TOP_SIGNAL_ENTRIES_CONFIG = TopSignalEntriesConfig()


async def get_top_signal_entries_config(session: AsyncSession) -> TopSignalEntriesConfig:
    """Effektív konfig: DB JSON vagy kód default."""
    raw = await get_runtime_raw(session, TOP_SIGNAL_ENTRIES_CONFIG_KEY)
    if raw is None:
        return DEFAULT_TOP_SIGNAL_ENTRIES_CONFIG.model_copy(deep=True)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return DEFAULT_TOP_SIGNAL_ENTRIES_CONFIG.model_copy(deep=True)
    if not isinstance(data, dict):
        return DEFAULT_TOP_SIGNAL_ENTRIES_CONFIG.model_copy(deep=True)
    return TopSignalEntriesConfig.model_validate(
        {**DEFAULT_TOP_SIGNAL_ENTRIES_CONFIG.model_dump(), **data}
    )


async def set_top_signal_entries_config(
    session: AsyncSession, patch: TopSignalEntriesConfigPatch
) -> TopSignalEntriesConfig:
    """Részleges mentés; visszaadja a teljes effektív konfigot."""
    current = await get_top_signal_entries_config(session)
    updates = {k: v for k, v in patch.model_dump().items() if v is not None}
    merged = current.model_copy(update=updates)
    await set_runtime_json_value(
        session, TOP_SIGNAL_ENTRIES_CONFIG_KEY, merged.model_dump()
    )
    return merged
