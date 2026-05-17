"""Hold-window integráció a walk-forward variációkkal."""

from __future__ import annotations

from decimal import Decimal

from app.services.coin_analyze import build_walk_forward_tpsl_variations_payload, parse_klines
from app.services.hold_window import HoldWindowParams


def _synthetic_klines(n: int = 80) -> list:
    rows = []
    base = Decimal("100")
    for i in range(n):
        t = i * 60 * 1000
        c = base + Decimal(i) * Decimal("0.05")
        rows.append(
            {
                "time": t,
                "open": c,
                "high": c + Decimal("0.5"),
                "low": c - Decimal("0.5"),
                "close": c + Decimal("0.1"),
            }
        )
    return rows


def test_wf_variations_include_hold_window_when_enabled() -> None:
    klines = parse_klines(_synthetic_klines(90))
    params = HoldWindowParams(
        enabled=True,
        min_minutes=30,
        max_minutes=35,
        step_minutes=5,
        profit_threshold_pct=Decimal("15"),
    )
    block = build_walk_forward_tpsl_variations_payload(
        klines,
        choppiness_max=Decimal("2.0"),
        cooldown_minutes=0,
        min_resolved_trades=1,
        hold_params=params,
    )
    assert block["enabled"]
    assert block["variations"]
    first = block["variations"][0]
    assert "hold_window" in first
    assert first["hold_window"]["enabled"] is True
    assert first["hold_window"]["grid_minutes"] == [30, 35]
