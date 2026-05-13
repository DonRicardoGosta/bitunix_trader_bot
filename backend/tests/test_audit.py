"""Audit DB-logger tesztek."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
import sqlalchemy as sa

from app.db import audit
from app.db.base import Base
from app.db.models import AuditEvent, AuditLevel
from app.db.session import AsyncSessionLocal, engine


@pytest.fixture(scope="module", autouse=True)
def _create_schema() -> None:
    asyncio.run(_create_all())


async def _create_all() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_record_event_persists_with_payload_and_level() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(AuditEvent))
        await audit.record(
            session,
            "test.audit",
            level=AuditLevel.WARNING,
            message="hello",
            payload={"qty": Decimal("0.001"), "symbol": "BTCUSDT"},
            strategy_name="unit_test",
        )
        await session.commit()

        result = await session.execute(sa.select(AuditEvent))
        row = result.scalar_one()
        assert row.event == "test.audit"
        assert row.level == AuditLevel.WARNING
        assert row.message == "hello"
        assert row.strategy_name == "unit_test"
        # Decimal -> str konverzió a _safe_payload-ban:
        assert row.payload == {"qty": "0.001", "symbol": "BTCUSDT"}


@pytest.mark.asyncio
async def test_record_isolated_uses_separate_session() -> None:
    """A record_isolated saját sessionnel commit-ol, akkor is, ha az outer rollback."""
    await audit.record_isolated(
        "test.isolated",
        level=AuditLevel.INFO,
        message="stays",
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            sa.select(AuditEvent).where(AuditEvent.event == "test.isolated")
        )
        assert result.scalar_one().message == "stays"


@pytest.mark.asyncio
async def test_list_events_filters_by_level_and_prefix() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(sa.delete(AuditEvent))
        await audit.record(session, "foo.one", level=AuditLevel.INFO)
        await audit.record(session, "foo.two", level=AuditLevel.ERROR)
        await audit.record(session, "bar.one", level=AuditLevel.INFO)
        await session.commit()

        errors = await audit.list_events(session, level="ERROR")
        assert [e.event for e in errors] == ["foo.two"]

        foos = await audit.list_events(session, event_prefix="foo.")
        assert {e.event for e in foos} == {"foo.one", "foo.two"}
