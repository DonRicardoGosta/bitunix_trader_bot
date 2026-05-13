"""Unit tesztek: rendelés lista gazdagítás (Bitunix válasz szimuláció nélkül)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.db.models import Order, OrderSide, OrderStatus, OrderType
from app.services.order_enrichment import (
    PositionMatch,
    TradeAugment,
    aggregate_trades_response,
    best_trade_augment,
    build_order_api_dict,
    build_trade_augment_indices,
    earliest_history_start_ms,
    extract_history_position_rows,
    extract_open_position_rows,
    index_history_orders_by_client_id,
    last_or_mark_price_from_ticker,
    margin_usdt_linear,
    match_position_for_order,
    parse_open_symbols_from_positions,
    pick_trade_augment,
    position_match_from_row,
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
    now = kwargs.get("created_at") or datetime.now(UTC)
    o.created_at = now  # type: ignore[assignment]
    o.updated_at = now  # type: ignore[assignment]
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


# ---- PositionMatch / match_position_for_order ----


def test_position_match_from_row_open() -> None:
    row = {
        "positionId": "pos-1",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "0.5",
        "leverage": 20,
        "realizedPNL": "-0.01",
        "unrealizedPNL": "1.25",
        "margin": "100",
        "avgOpenPrice": "60000",
    }
    pm = position_match_from_row(row, is_open=True)
    assert pm.is_open is True
    assert pm.position_id == "pos-1"
    assert pm.realized_pnl == Decimal("-0.01")
    assert pm.unrealized_pnl == Decimal("1.25")
    assert pm.margin == Decimal("100")
    assert pm.entry_price == Decimal("60000")
    assert pm.leverage == 20


def test_position_match_from_row_history_uses_entry_and_close_price() -> None:
    row = {
        "positionId": "pos-2",
        "symbol": "SAGAUSDT",
        "side": "SELL",
        "maxQty": "468.6",
        "entryPrice": "0.02811",
        "closePrice": "0.02804",
        "leverage": "50",
        "realizedPNL": "0.0170",
        "fee": "0.0157",
    }
    pm = position_match_from_row(row, is_open=False)
    assert pm.is_open is False
    assert pm.unrealized_pnl == Decimal(0)
    assert pm.entry_price == Decimal("0.02811")
    assert pm.close_price == Decimal("0.02804")
    assert pm.qty == Decimal("468.6")
    assert pm.leverage == 50


def test_match_position_for_order_picks_open_within_tolerance() -> None:
    """Entry rendelés ctime ≈ pozíció ctime → nyitott pozícióval párosítson."""
    # Order created_at: 2025-11-09 14:30:38.891 UTC (a probe SAGAUSDT order ctime-ja)
    when = datetime.fromtimestamp(1778681838.891, tz=UTC)
    o = _order(
        client_order_id="bt-1a3ee0b6",
        symbol="SAGAUSDT",
        quantity="468.6",
        leverage=50,
        side=OrderSide.SELL,
        created_at=when,
    )
    open_rows = [
        {
            "positionId": "open-1",
            "symbol": "SAGAUSDT",
            "side": "SELL",
            "qty": "468.6",
            "leverage": 50,
            "ctime": "1778681838000",  # ms, 891 ms különbség
            "realizedPNL": "-0.008",
            "unrealizedPNL": "0.05",
            "margin": "0.26",
            "avgOpenPrice": "0.02811",
        }
    ]
    pm = match_position_for_order(
        o, open_position_rows=open_rows, history_position_rows=[]
    )
    assert pm is not None
    assert pm.position_id == "open-1"
    assert pm.is_open is True


def test_match_position_for_order_picks_history_when_no_open() -> None:
    when = datetime.fromtimestamp(1778681838.0, tz=UTC)
    o = _order(
        client_order_id="bt-x",
        symbol="SAGAUSDT",
        quantity="468.6",
        leverage=50,
        side=OrderSide.SELL,
        created_at=when,
    )
    history_rows = [
        {
            "positionId": "hist-1",
            "symbol": "SAGAUSDT",
            "side": "SELL",
            "maxQty": "468.6",
            "leverage": "50",
            "ctime": "1778681838000",
            "entryPrice": "0.02811",
            "closePrice": "0.02804",
            "realizedPNL": "0.017014866",
        }
    ]
    pm = match_position_for_order(
        o, open_position_rows=[], history_position_rows=history_rows
    )
    assert pm is not None
    assert pm.position_id == "hist-1"
    assert pm.is_open is False
    assert pm.realized_pnl == Decimal("0.017014866")


def test_match_position_for_order_rejects_when_outside_tolerance() -> None:
    when = datetime.fromtimestamp(1778681838.0, tz=UTC)
    o = _order(
        client_order_id="bt-x",
        symbol="SAGAUSDT",
        quantity="1",
        side=OrderSide.SELL,
        created_at=when,
    )
    history_rows = [
        {
            "positionId": "old",
            "symbol": "SAGAUSDT",
            "side": "SELL",
            "ctime": "1778681500000",  # 338s eltérés
            "realizedPNL": "1.0",
            "entryPrice": "1",
            "leverage": "10",
            "qty": "1",
        }
    ]
    pm = match_position_for_order(
        o, open_position_rows=[], history_position_rows=history_rows
    )
    assert pm is None


def test_match_position_for_order_filters_by_side() -> None:
    """HEDGE módban azonos symbol-on lehet LONG és SHORT egyszerre."""
    when = datetime.fromtimestamp(1778681838.0, tz=UTC)
    o = _order(
        client_order_id="bt-x",
        symbol="BTCUSDT",
        quantity="1",
        side=OrderSide.BUY,
        created_at=when,
    )
    open_rows = [
        {
            "positionId": "wrong-side",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "ctime": "1778681838000",
            "realizedPNL": "10",
            "unrealizedPNL": "1",
            "margin": "100",
            "leverage": 10,
            "qty": "1",
            "avgOpenPrice": "1",
        }
    ]
    pm = match_position_for_order(
        o, open_position_rows=open_rows, history_position_rows=[]
    )
    assert pm is None


def test_match_position_skips_reduce_only_orders() -> None:
    """Záró rendeléseknél a saját realizedPNL már jó a hist_orders-ből."""
    o = _order(
        client_order_id="bt-close",
        symbol="BTCUSDT",
        quantity="1",
        side=OrderSide.SELL,
        reduce_only=True,
    )
    pm = match_position_for_order(
        o,
        open_position_rows=[{
            "positionId": "p", "symbol": "BTCUSDT", "side": "SELL", "ctime": "0",
            "realizedPNL": "0", "unrealizedPNL": "0", "margin": "1", "leverage": 1,
            "qty": "1", "avgOpenPrice": "1",
        }],
        history_position_rows=[],
    )
    assert pm is None


def test_extract_open_position_rows_passthrough() -> None:
    raw = {
        "code": 0,
        "data": [
            {"symbol": "BTCUSDT", "positionAmt": "1"},
            {"symbol": "ETHUSDT", "positionAmt": "0"},
        ],
    }
    rows = extract_open_position_rows(raw)
    assert len(rows) == 2
    assert rows[0]["symbol"] == "BTCUSDT"


def test_extract_history_position_rows_supports_nested_list() -> None:
    raw = {
        "code": 0,
        "data": {
            "total": "2",
            "positionList": [
                {"positionId": "a", "symbol": "BTCUSDT"},
                {"positionId": "b", "symbol": "ETHUSDT"},
            ],
        },
    }
    rows = extract_history_position_rows(raw)
    assert [r["positionId"] for r in rows] == ["a", "b"]


# ---- build_order_api_dict pozíció-szintű ágak ----


def test_build_order_with_open_position_uses_unrealized_in_roi() -> None:
    """Nyitott pozíción a ROI = (realized + unrealized) / margin * 100."""
    o = _order(
        client_order_id="bt-open",
        symbol="MLNUSDT",
        quantity="5.81",
        leverage=50,
        side=OrderSide.SELL,
    )
    pm = PositionMatch(
        position_id="pos-open",
        side="SELL",
        is_open=True,
        realized_pnl=Decimal("-0.007679658"),
        unrealized_pnl=Decimal("0.05229"),
        margin=Decimal("0.263668258"),
        entry_price=Decimal("2.203"),
        close_price=None,
        qty=Decimal("5.81"),
        leverage=50,
    )
    out = build_order_api_dict(
        o, hist_row=None, open_symbols={"MLNUSDT"}, position_match=pm
    )
    ex = out["exchange"]
    assert ex["lifecycle"] == "open"
    assert ex["realized_pnl_usdt"] == "-0.007679658"
    assert ex["unrealized_pnl_usdt"] == "0.05229"
    # (-0.007679658 + 0.05229) / 0.263668258 * 100 = 16.91...
    assert ex["roi_pct"] == "16.92"
    assert ex["margin_usdt_estimate"] == "0.2637"
    assert ex["position_id"] == "pos-open"


def test_build_order_with_closed_position_uses_realized_only() -> None:
    o = _order(
        client_order_id="bt-closed",
        symbol="SAGAUSDT",
        quantity="468.6",
        leverage=50,
        side=OrderSide.SELL,
    )
    pm = PositionMatch(
        position_id="pos-closed",
        side="SELL",
        is_open=False,
        realized_pnl=Decimal("0.017014866"),
        unrealized_pnl=Decimal(0),
        margin=None,  # history-positions nem ad margint
        entry_price=Decimal("0.02811"),
        close_price=Decimal("0.02804"),
        qty=Decimal("468.6"),
        leverage=50,
    )
    out = build_order_api_dict(
        o, hist_row=None, open_symbols=set(), position_match=pm
    )
    ex = out["exchange"]
    assert ex["lifecycle"] == "closed"
    assert ex["realized_pnl_usdt"] == "0.017014866"
    assert ex["unrealized_pnl_usdt"] is None
    # Margin nélkül a Bitunix nem ad explicit margint → qty*entry/lev fallback:
    # 468.6 * 0.02811 / 50 = 0.26343492
    assert ex["margin_usdt_estimate"] == "0.2634"
    # ROI = 0.017014866 / 0.26343492 * 100 ≈ 6.46%
    assert ex["roi_pct"] == "6.46"
