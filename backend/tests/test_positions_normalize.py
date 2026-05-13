"""Unit tesztek: ``positions_normalize`` modul."""

from __future__ import annotations

from decimal import Decimal

from app.services.positions_normalize import (
    normalize_open_positions_response,
    normalize_position_row,
)


def test_normalize_open_position_basic() -> None:
    row = {
        "positionId": "pid-1",
        "symbol": "BTCUSDT",
        "qty": "0.5",
        "side": "BUY",
        "leverage": 20,
        "marginMode": "CROSS",
        "positionMode": "HEDGE",
        "avgOpenPrice": "60000",
        "markPrice": "61000",
        "margin": "1500",
        "realizedPNL": "-0.5",
        "unrealizedPNL": "500",
        "liqPrice": "55000",
        "ctime": "1778681838000",
        "mtime": "1778682838000",
    }
    out = normalize_position_row(row)
    assert out["symbol"] == "BTCUSDT"
    assert out["side"] == "BUY"
    assert out["qty"] == "0.5"
    assert out["leverage"] == 20
    assert out["entry_price"] == "60000"
    assert out["mark_price"] == "61000"
    assert out["margin"] == "1500"
    assert out["realized_pnl"] == "-0.5"
    assert out["unrealized_pnl"] == "500"
    assert out["liq_price"] == "55000"
    # ROI = (-0.5 + 500) / 1500 * 100 = 33.30
    assert out["roi_pct"] == "33.30"
    assert out["margin_mode"] == "CROSS"
    assert out["position_mode"] == "HEDGE"
    assert out["opened_at"] is not None and "T" in out["opened_at"]


def test_normalize_position_handles_missing_margin() -> None:
    """Ha nincs margin, ROI is None."""
    row = {
        "symbol": "BTCUSDT",
        "qty": "1",
        "side": "BUY",
        "avgOpenPrice": "100",
        "realizedPNL": "0",
        "unrealizedPNL": "0",
    }
    out = normalize_position_row(row)
    assert out["margin"] is None
    assert out["roi_pct"] is None


def test_normalize_open_positions_response_totals() -> None:
    raw = {
        "code": 0,
        "data": [
            {
                "positionId": "p1",
                "symbol": "BTCUSDT",
                "qty": "1",
                "side": "BUY",
                "leverage": 10,
                "avgOpenPrice": "60000",
                "markPrice": "60500",
                "margin": "6000",
                "realizedPNL": "-1",
                "unrealizedPNL": "500",
            },
            {
                "positionId": "p2",
                "symbol": "ETHUSDT",
                "qty": "10",
                "side": "SELL",
                "leverage": 5,
                "avgOpenPrice": "3000",
                "markPrice": "2990",
                "margin": "6000",
                "realizedPNL": "0",
                "unrealizedPNL": "100",
            },
        ],
    }
    out = normalize_open_positions_response(raw)
    assert len(out["positions"]) == 2
    t = out["totals"]
    assert t["count"] == 2
    assert Decimal(t["unrealized_pnl_usdt"]) == Decimal("600")
    assert Decimal(t["margin_usdt"]) == Decimal("12000")
    assert Decimal(t["realized_pnl_usdt"]) == Decimal("-1")


def test_normalize_open_positions_response_empty() -> None:
    out = normalize_open_positions_response({"code": 0, "data": []})
    assert out["positions"] == []
    assert out["totals"]["count"] == 0
    assert out["totals"]["unrealized_pnl_usdt"] == "0"
