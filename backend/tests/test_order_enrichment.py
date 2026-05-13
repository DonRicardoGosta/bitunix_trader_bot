"""Unit tesztek: rendelés lista gazdagítás (Bitunix válasz szimuláció nélkül)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.db.models import Order, OrderSide, OrderStatus, OrderType
from app.services.order_enrichment import (
    TradeAugment,
    aggregate_trades_response,
    best_trade_augment,
    build_order_api_dict,
    build_trade_augment_indices,
    earliest_history_start_ms,
    index_history_orders_by_client_id,
    last_or_mark_price_from_ticker,
    margin_usdt_linear,
    parse_open_symbols_from_positions,
    pick_trade_augment,
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


def test_roi_uses_trade_vwap_when_hist_price_zero() -> None:
    """MARKET history sor price=0 esetén a trade-history VWAP számít marginhoz."""
    o = _order(
        client_order_id="bt-z",
        symbol="XUSDT",
        quantity="1",
        price=None,
        leverage=10,
    )
    hist = {
        "status": "FILLED",
        "realizedPNL": "10",
        "tradeQty": "1",
        "price": "0",
        "leverage": 10,
        "mtime": 1,
    }
    aug = TradeAugment(realized_sum=Decimal("10"), avg_price=Decimal("100"))
    out = build_order_api_dict(o, hist_row=hist, open_symbols=set(), trade_augment=aug)
    assert out["exchange"]["roi_pct"] == "100.00"


def test_roi_zero_with_mark_price_only() -> None:
    o = _order(
        client_order_id="bt-m",
        symbol="YUSDT",
        quantity="2",
        price=None,
        leverage=5,
    )
    hist = {
        "status": "FILLED",
        "realizedPNL": "0",
        "tradeQty": "2",
        "price": "0",
        "leverage": 5,
        "mtime": 1,
    }
    out = build_order_api_dict(
        o,
        hist_row=hist,
        open_symbols=set(),
        trade_augment=None,
        mark_price=Decimal("50"),
    )
    assert out["exchange"]["roi_pct"] == "0.00"


def test_build_trade_augment_indices_vwap() -> None:
    resp = {
        "data": {
            "tradeList": [
                {
                    "clientId": "c1",
                    "orderId": "99",
                    "qty": "1",
                    "price": "100",
                    "realizedPNL": "0",
                },
                {
                    "clientId": "c1",
                    "orderId": "99",
                    "qty": "1",
                    "price": "200",
                    "realizedPNL": "5",
                },
            ]
        }
    }
    by_c, by_o = build_trade_augment_indices(resp)
    assert by_c["c1"].avg_price == Decimal("150")
    assert by_c["c1"].realized_sum == Decimal("5")
    assert by_o["99"].avg_price == Decimal("150")


def test_last_or_mark_price_from_ticker() -> None:
    raw = {"data": [{"markPrice": "1.5", "lastPrice": "2"}]}
    assert last_or_mark_price_from_ticker(raw) == Decimal("1.5")


def test_extract_order_list_accepts_data_as_list() -> None:
    resp = {
        "code": 0,
        "data": [
            {
                "clientId": "bt-test",
                "orderId": "99",
                "status": "FILLED",
                "mtime": 1,
                "realizedPNL": "3",
            }
        ],
    }
    idx = index_history_orders_by_client_id(resp)
    assert idx["bt-test"]["status"] == "FILLED"


def test_aggregate_trades_response() -> None:
    resp = {
        "data": {
            "tradeList": [
                {"qty": "1", "price": "100", "realizedPNL": "1"},
                {"qty": "1", "price": "200", "realizedPNL": "2"},
            ]
        }
    }
    agg = aggregate_trades_response(resp)
    assert agg.realized_sum == Decimal("3")
    assert agg.avg_price == Decimal("150")


def test_best_trade_augment_prefers_larger_abs_pnl() -> None:
    a = TradeAugment(Decimal("1"), Decimal("100"))
    b = TradeAugment(Decimal("-50"), Decimal("0"))
    assert best_trade_augment(a, b) == b


def test_earliest_history_start_ms() -> None:
    o = _order(client_order_id="a", symbol="S", quantity="1", price="1")
    ms = earliest_history_start_ms([o], "S")
    assert ms is not None


def test_pick_trade_augment_prefers_client_with_price() -> None:
    by_c = {"a": TradeAugment(Decimal(0), Decimal("10"))}
    by_o = {"b": TradeAugment(Decimal(0), Decimal("20"))}
    assert pick_trade_augment(by_c, by_o, client_order_id="a", bitunix_order_id="b") == by_c["a"]


def test_build_order_open_overrides_filled_row() -> None:
    o = _order(client_order_id="bt-y", symbol="ETHUSDT", quantity="1", price="2000", leverage=5)
    hist = {"status": "FILLED", "realizedPNL": "0", "qty": "1", "price": "2000", "leverage": 5}
    out = build_order_api_dict(o, hist_row=hist, open_symbols={"ETHUSDT"})
    assert out["exchange"]["lifecycle"] == "open"


def test_build_order_api_dict_include_debug() -> None:
    o = _order(client_order_id="bt-dbg", symbol="ZUSDT", quantity="1", price=None, leverage=5)
    hist = {"status": "FILLED", "realizedPNL": "0", "qty": "1", "price": "0", "clientId": "bt-dbg"}
    out = build_order_api_dict(
        o,
        hist_row=hist,
        open_symbols=set(),
        include_debug=True,
        debug_extras={"note": "unit"},
    )
    assert out["exchange"]["debug"]["history_row_found"] is True
    assert "roi_blocked" in out["exchange"]["debug"]
    assert out["exchange"]["debug"]["extras"]["note"] == "unit"
