"""Stratégia runtime konfig DB + default tesztek."""

from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa

from app.db.base import Base
from app.db.models import AppRuntimeSetting
from app.db.session import AsyncSessionLocal, engine
from app.schemas.strategy_config import TopSignalEntriesConfigPatch
from app.services.strategy_runtime_config import (
    DEFAULT_TOP_SIGNAL_ENTRIES_CONFIG,
    get_top_signal_entries_config,
    set_top_signal_entries_config,
)


@pytest.fixture(scope="module", autouse=True)
def _schema() -> None:
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _clear_config() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(AppRuntimeSetting))
        await session.commit()


@pytest.mark.asyncio
async def test_default_config_when_db_empty() -> None:
    await _clear_config()
    async with AsyncSessionLocal() as session:
        cfg = await get_top_signal_entries_config(session)
    assert cfg.count == DEFAULT_TOP_SIGNAL_ENTRIES_CONFIG.count
    assert cfg.scan_limit == 500
    assert cfg.kline_lookahead == 200
    assert cfg.wf_gate_enabled is False
    assert cfg.wf_lookback_minutes == 4320


@pytest.mark.asyncio
async def test_config_patch_persists() -> None:
    await _clear_config()
    async with AsyncSessionLocal() as session:
        saved = await set_top_signal_entries_config(
            session,
            TopSignalEntriesConfigPatch(count=5, wf_gate_enabled=False),
        )
        await session.commit()
    assert saved.count == 5
    assert saved.wf_gate_enabled is False
    async with AsyncSessionLocal() as session:
        loaded = await get_top_signal_entries_config(session)
    assert loaded.count == 5
    assert loaded.wf_gate_enabled is False
    assert loaded.scan_limit == DEFAULT_TOP_SIGNAL_ENTRIES_CONFIG.scan_limit
