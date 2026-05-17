"""Runtime beállítások (DB) + env effektív értékek összevonása."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import AppRuntimeSetting
from app.services.trading_blackout import (
    get_trading_blackout_schedule,
    is_new_position_open_blocked,
)

# UI-ból módosítható kulcsok (bool).
RUNTIME_BOOL_KEYS: frozenset[str] = frozenset(
    {
        "trading_paused",
        "require_calibration_for_trading",
        "strategy_runner_paused",
        "strategy_top_signal_entries_enabled",
    }
)

_STRATEGY_ENV_MAP: dict[str, str] = {
    "top_signal_entries": "strategy_top_signal_entries_enabled",
}


async def get_runtime_raw(session: AsyncSession, key: str) -> str | None:
    row = await session.get(AppRuntimeSetting, key)
    return row.value if row is not None else None


async def get_runtime_bool(session: AsyncSession, key: str) -> bool | None:
    raw = await get_runtime_raw(session, key)
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(parsed, bool):
        return parsed
    return bool(parsed)


async def set_runtime_bool(session: AsyncSession, key: str, value: bool) -> None:
    if key not in RUNTIME_BOOL_KEYS:
        raise ValueError(f"Unsupported runtime key: {key}")
    existing = await session.get(AppRuntimeSetting, key)
    encoded = json.dumps(value)
    if existing is None:
        session.add(AppRuntimeSetting(key=key, value=encoded))
    else:
        existing.value = encoded
        existing.updated_at = datetime.now(UTC)


def _env_bool(settings: Settings, attr: str) -> bool:
    return bool(getattr(settings, attr))


async def effective_bool(
    session: AsyncSession,
    settings: Settings,
    *,
    runtime_key: str,
    env_attr: str,
) -> bool:
    override = await get_runtime_bool(session, runtime_key)
    if override is not None:
        return override
    return _env_bool(settings, env_attr)


async def is_trading_paused(session: AsyncSession) -> bool:
    override = await get_runtime_bool(session, "trading_paused")
    return override if override is not None else False


async def effective_require_calibration(
    session: AsyncSession, settings: Settings
) -> bool:
    return await effective_bool(
        session,
        settings,
        runtime_key="require_calibration_for_trading",
        env_attr="require_calibration_for_trading",
    )


async def is_strategy_runner_paused(session: AsyncSession, settings: Settings) -> bool:
    override = await get_runtime_bool(session, "strategy_runner_paused")
    return override if override is not None else False


async def is_strategy_enabled(
    session: AsyncSession, settings: Settings, strategy_name: str
) -> bool:
    env_attr = _STRATEGY_ENV_MAP.get(strategy_name)
    if env_attr is None:
        return True
    runtime_key = env_attr
    return await effective_bool(session, settings, runtime_key=runtime_key, env_attr=env_attr)


async def build_settings_snapshot(session: AsyncSession) -> dict[str, Any]:
    """Frontend control center — env + runtime effektív állapot."""
    settings = get_settings()
    trading_paused = await is_trading_paused(session)
    require_cal = await effective_require_calibration(session, settings)
    runner_paused = await is_strategy_runner_paused(session, settings)

    strategies: dict[str, bool] = {}
    for name in _STRATEGY_ENV_MAP:
        strategies[name] = await is_strategy_enabled(session, settings, name)

    blocked, block_reason = await is_new_position_open_blocked(session)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "env": {
            "app_env": settings.app_env,
            "bitunix_live_trading": settings.bitunix_live_trading,
            "strategy_runner_enabled": settings.strategy_runner_enabled,
            "calibration_enabled": settings.calibration_enabled,
            "require_calibration_for_trading": settings.require_calibration_for_trading,
            "strategy_top_signal_entries_enabled": (
                settings.strategy_top_signal_entries_enabled
            ),
        },
        "effective": {
            "trading_paused": trading_paused,
            "require_calibration_for_trading": require_cal,
            "strategy_runner_paused": runner_paused,
            "strategy_runner_active": (
                settings.strategy_runner_enabled and not runner_paused
            ),
            "live_trading": settings.bitunix_live_trading,
            "strategies": strategies,
            "new_position_open_allowed": not blocked,
            "new_position_block_reason": block_reason,
        },
        "trading_blackout": await get_trading_blackout_schedule(session),
        "runtime_overrides": await _list_overrides(session),
        "strategy_config": {
            "interval_seconds": settings.strategy_interval_seconds,
            "top_signal_entries_count": settings.strategy_top_signal_entries_count,
            "top_signal_entries_cooldown_minutes": (
                settings.strategy_top_signal_entries_cooldown_minutes
            ),
            "top_signal_entries_scan_limit": (
                settings.strategy_top_signal_entries_scan_limit
            ),
            "calibration_interval_seconds": settings.calibration_interval_seconds,
            "calibration_max_age_minutes": settings.calibration_max_age_minutes,
        },
    }


async def _list_overrides(session: AsyncSession) -> dict[str, bool]:
    rows = (
        await session.execute(
            sa.select(AppRuntimeSetting).where(
                AppRuntimeSetting.key.in_(RUNTIME_BOOL_KEYS)
            )
        )
    ).scalars().all()
    out: dict[str, bool] = {}
    for row in rows:
        val = await get_runtime_bool(session, row.key)
        if val is not None:
            out[row.key] = val
    return out


async def apply_settings_patch(
    session: AsyncSession, patch: dict[str, bool]
) -> dict[str, bool]:
    """Csak engedélyezett kulcsok; visszaadja a friss runtime override-okat."""
    applied: dict[str, bool] = {}
    for key, value in patch.items():
        if key not in RUNTIME_BOOL_KEYS:
            raise ValueError(f"Unsupported key: {key}")
        await set_runtime_bool(session, key, bool(value))
        applied[key] = bool(value)
    return applied
