"""Unit tesztek: rendelés lista gazdagítás (Bitunix válasz szimuláció nélkül)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.db.models import Order, OrderSide, OrderStatus, OrderType
from app.services.order_enrichment import (
    build_order_api_dict,
    index_history_orders_by_client_id,
    margin_usdt_linear,
    parse_open_symbols_from_positions,
)


def _order(**kwargs: object) -> Order:
    o = Order(
        id=int(kwargs.get("id", 1)),
        client_order_id=str(kwargs["client_order_id"]),
        bitunix_order_id=kwargs.get("bitunix_order_id"),
        symbol=str(kwargs["symbol"]),
        side=kwargs.get("side", OrderSide.BUY),
        type=kwargs.get("type", OrderType.MARKET),
        quantity=Decimal(str(kwargs["quantity"])),
        price=kwargs.get("price"),
        leverage=int(kwargs.get("leverage", 10)),
        status=kwargs.get("status", OrderStatus.NEW),
        reduce_only=bool(kwargs.get("reduce_only", False)),
        strategy_name=kwargs.get("strategy_name"),
    )
    now = datetime.now(UTC)
    o.created_at = now
    o.updated_at = now
    return o


def test_margin_usdt_linear() -> None:
    m = margin_usdt_linear(qty=Decimal("2"), price=Decimal("30000"), leverage=10)
    assert m == Decimal("6000")


def test_parse_open_symbols_from_positions() -> None:
    raw = {
        "data": [
            {"symbol": "AAAUSDT", "positionAmt": "0"},
            {"symbol": "BBBUSDT", "positionAmt": "1.5"},
        ]
    }
    assert parse_open_symbols_from_positions(raw) == {"BBBUSDT"}


def test_index_history_orders_by_client_id_latest_mtime() -> None:
    resp = {
        "data": {
            "orderList": [
                {
                    "clientId": "c1",
                    "status": "NEW",
                    "mtime": 100,
                    "realizedPNL": "0",
                    "qty": "1",
                    "price": "10",
                    "leverage": 5,
                },
                {
                    "clientId": "c1",
                    "status": "FILLED",
                    "mtime": 200,
                    "realizedPNL": "5",
                    "tradeQty": "1",
                    "price": "10",
                    "leverage": 5,
                },
            ]
        }
    }
    idx = index_history_orders_by_client_id(resp)
    assert idx["c1"]["status"] == "FILLED"


def test_build_order_closed_roi() -> None:
    o = _order(
        client_order_id="bt-x",
        symbol="BTCUSDT",
        quantity="1",
        price="100",
        leverage=10,
    )
    hist = {
        "status": "FILLED",
        "realizedPNL": "25",
        "tradeQty": "1",
        "price": "100",
        "leverage": 10,
        "mtime": 1,
    }
    out = build_order_api_dict(o, hist_row=hist, open_symbols=set())
    assert out["exchange"]["lifecycle"] == "closed"
    assert out["exchange"]["roi_pct"] == "250.00"  # 25 / (1*100/10) * 100


def test_build_order_open_overrides_filled_row() -> None:
    o = _order(client_order_id="bt-y", symbol="ETHUSDT", quantity="1", price="2000", leverage=5)
    hist = {"status": "FILLED", "realizedPNL": "0", "qty": "1", "price": "2000", "leverage": 5}
    out = build_order_api_dict(o, hist_row=hist, open_symbols={"ETHUSDT"})
    assert out["exchange"]["lifecycle"] == "open"
