"""Authoritatív, DB-be írt eseménynapló.

Ez a modul a futási események egyetlen kötelező csatornája. Nincs külön
fájl / stdout-only log a business események számára – minden ami fontos,
ide kerül.

Két használati mód:

1. **Megosztott sessionben:** ha már van nyitott DB session, és a hívást
   abból a tranzakcióból akarjuk lefuttatni:

       await record(session, "strategy.signal", message="...", payload={...})

2. **Saját sessionben (tűzfalas):** ha hibakezelés közben akarunk logolni
   és nem szeretnénk az outer tranzakciót megzavarni:

       await record_isolated("strategy.error", level=AuditLevel.ERROR, ...)
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent, AuditLevel
from app.db.session import AsyncSessionLocal


async def record(
    session: AsyncSession,
    event: str,
    *,
    level: AuditLevel | str = AuditLevel.INFO,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
    strategy_name: str | None = None,
    commit: bool = False,
) -> AuditEvent:
    """Esemény rögzítése a megadott sessionben.

    Args:
        session: Megosztott DB session.
        event: Dot-notation eseménykulcs (pl. ``strategy.top_movers.signal``).
        level: ``AuditLevel`` érték vagy név.
        message: Rövid emberi olvasásra szánt üzenet.
        payload: Tetszőleges JSON-elizálható kontextus.
        strategy_name: Kapcsolódó stratégia neve (ha van).
        commit: Ha True, a hívás után commit-ol.

    Returns:
        A perzisztált ``AuditEvent``.
    """
    if isinstance(level, str):
        level = AuditLevel(level.upper())
    entry = AuditEvent(
        level=level,
        event=event,
        message=message,
        payload=_safe_payload(payload),
        strategy_name=strategy_name,
    )
    session.add(entry)
    await session.flush()
    if commit:
        await session.commit()
    return entry


async def record_isolated(
    event: str,
    *,
    level: AuditLevel | str = AuditLevel.INFO,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
    strategy_name: str | None = None,
) -> None:
    """Esemény rögzítése külön, friss sessionben (commit-tel).

    Akkor használd, ha hiba-ágban vagy és az outer tranzakció már piszkos.
    """
    async with AsyncSessionLocal() as session:
        await record(
            session,
            event,
            level=level,
            message=message,
            payload=payload,
            strategy_name=strategy_name,
            commit=True,
        )


async def list_events(
    session: AsyncSession,
    *,
    level: str | None = None,
    event_prefix: str | None = None,
    strategy_name: str | None = None,
    limit: int = 100,
) -> list[AuditEvent]:
    """Esemény lekérdezés szűrőkkel, idő szerint csökkenő sorrendben."""
    stmt = sa.select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if level:
        stmt = stmt.where(AuditEvent.level == AuditLevel(level.upper()))
    if event_prefix:
        stmt = stmt.where(AuditEvent.event.like(f"{event_prefix}%"))
    if strategy_name:
        stmt = stmt.where(AuditEvent.strategy_name == strategy_name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _safe_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """A payloadot JSON-elhetővé teszi (Decimal → str stb.)."""
    if payload is None:
        return None
    return _coerce(payload)


def _coerce(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _coerce(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_coerce(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    return str(value)
