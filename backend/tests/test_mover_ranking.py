"""Mover rangsorolás és irány-döntés unit tesztek (kliens nélkül)."""

from __future__ import annotations

from decimal import Decimal

from app.services.strategy.mover_ranking import (
    Mover,
    decide_direction,
    extract_available_usdt,
    movers_for_symbols,
    parse_open_position_symbols,
    rank_top_movers,
)
from app.services.trading_pairs_meta import index_trading_pairs


def test_rank_top_movers_uses_absolute_change() -> None:
    """A rangsorolás abszolút % alapján – nagy esés is bekerülhet."""
    raw = {
        "data": [
            {"symbol": "AAA", "lastPrice": "110", "open": "100"},  # +10%
            {"symbol": "BBB", "lastPrice": "70", "open": "100"},  # -30%  (abs 30)
            {"symbol": "CCC", "lastPrice": "105", "open": "100"},  # +5%
            {"symbol": "DDD", "lastPrice": "85", "open": "100"},  # -15%  (abs 15)
        ]
    }
    top3 = rank_top_movers(raw, top_n=3)
    assert [m.symbol for m in top3] == ["BBB", "DDD", "AAA"]
    assert top3[0].change_pct == Decimal("-30")
    assert top3[1].change_pct == Decimal("-15")


def test_rank_top_movers_skips_invalid_rows() -> None:
    """Hiányos sorok kihagyva, nem dobnak hibát."""
    raw = {
        "data": [
            {"symbol": "AAA", "lastPrice": "110", "open": "100"},
            {"symbol": "BBB"},  # nincs ár
            {"symbol": "CCC", "lastPrice": "100", "open": "0"},  # /0
            {"lastPrice": "100", "open": "100"},  # nincs symbol
        ]
    }
    top = rank_top_movers(raw, top_n=10)
    assert [m.symbol for m in top] == ["AAA"]


def test_movers_for_symbols_filters_and_sorts() -> None:
    raw = {
        "data": [
            {"symbol": "AAA", "lastPrice": "110", "open": "100"},
            {"symbol": "BBB", "lastPrice": "70", "open": "100"},
            {"symbol": "CCC", "lastPrice": "105", "open": "100"},
        ]
    }
    out = movers_for_symbols(raw, {"BBB", "CCC"})
    assert [m.symbol for m in out] == ["BBB", "CCC"]


def test_rank_top_movers_accepts_bare_list() -> None:
    """Néha a data eleve lista – mindkettő működjön."""
    raw = [
        {"symbol": "X", "lastPrice": "200", "open": "100"},
        {"symbol": "Y", "lastPrice": "50", "open": "100"},
    ]
    top = rank_top_movers(raw, top_n=2)
    assert top[0].symbol == "X"
    assert abs(top[0].change_pct) >= abs(top[1].change_pct)


def test_index_trading_pairs_returns_max_leverage_per_symbol() -> None:
    raw = {
        "data": [
            {
                "symbol": "BTCUSDT",
                "maxLeverage": "125",
                "basePrecision": "3",
                "pricePrecision": "2",
            },
            {"symbol": "ETHUSDT", "maxLeverage": "100", "basePrecision": "2"},
            {"symbol": "WEIRD"},  # hiányos – default 1x és 4 tizedes
        ]
    }
    index = index_trading_pairs(raw)
    assert index["BTCUSDT"].max_leverage == 125
    assert index["BTCUSDT"].base_precision == 3
    assert index["BTCUSDT"].price_precision == 2
    assert index["ETHUSDT"].max_leverage == 100
    assert index["ETHUSDT"].price_precision == 4
    assert index["WEIRD"].max_leverage == 1
    assert index["WEIRD"].base_precision == 4


def test_extract_available_usdt_from_account_payload() -> None:
    raw = {"code": 0, "data": {"available": "123.45", "frozen": "1"}}
    assert extract_available_usdt(raw) == Decimal("123.45")


def test_extract_available_usdt_empty() -> None:
    assert extract_available_usdt({}) == Decimal("0")
    assert extract_available_usdt({"data": {}}) == Decimal("0")


def _mover(symbol: str, change: str, last: str, high: str, low: str) -> Mover:
    return Mover(
        symbol=symbol,
        last_price=Decimal(last),
        change_pct=Decimal(change),
        high=Decimal(high),
        low=Decimal(low),
    )


def test_decide_direction_trend_mode_follows_sign() -> None:
    up = _mover("X", "+5", "105", "110", "95")
    down = _mover("Y", "-7", "93", "100", "90")
    assert decide_direction(up, mode="trend", range_threshold=Decimal("0.66"))[0] == "BUY"
    assert decide_direction(down, mode="trend", range_threshold=Decimal("0.66"))[0] == "SELL"


def test_decide_direction_mean_revert_inverts_sign() -> None:
    up = _mover("X", "+5", "105", "110", "95")
    down = _mover("Y", "-7", "93", "100", "90")
    assert decide_direction(up, mode="mean_revert", range_threshold=Decimal("0.66"))[0] == "SELL"
    assert decide_direction(down, mode="mean_revert", range_threshold=Decimal("0.66"))[0] == "BUY"


def test_decide_direction_momentum_breakout_buys_near_high() -> None:
    """Pozitív változás + ár a 24h tartomány felső harmadában → BUY."""
    near_high = _mover("X", "+10", "108", "110", "90")  # pos = 18/20 = 0.9
    side, reason = decide_direction(
        near_high, mode="momentum_breakout", range_threshold=Decimal("0.66")
    )
    assert side == "BUY"
    assert "breakout" in reason


def test_decide_direction_momentum_breakout_sells_near_low() -> None:
    """Negatív változás + ár a 24h tartomány alsó harmadában → SELL."""
    near_low = _mover("Y", "-10", "92", "110", "90")  # pos = 2/20 = 0.1
    side, reason = decide_direction(
        near_low, mode="momentum_breakout", range_threshold=Decimal("0.66")
    )
    assert side == "SELL"
    assert "breakdown" in reason


def test_decide_direction_momentum_breakout_skips_ambiguous() -> None:
    """Pozitív változás, de ár középen → kétértelmű, SKIP."""
    mid = _mover("Z", "+15", "100", "110", "90")  # pos = 0.5
    side, reason = decide_direction(
        mid, mode="momentum_breakout", range_threshold=Decimal("0.66")
    )
    assert side is None
    assert "mixed" in reason


def test_decide_direction_no_range_data() -> None:
    """Ha nincs high/low, momentum_breakout módban SKIP."""
    bare = Mover(
        symbol="X",
        last_price=Decimal("100"),
        change_pct=Decimal("5"),
        high=None,
        low=None,
    )
    side, reason = decide_direction(
        bare, mode="momentum_breakout", range_threshold=Decimal("0.66")
    )
    assert side is None
    assert reason == "no_range_data"


def test_parse_open_position_symbols_filters_zero_size() -> None:
    raw = {
        "data": [
            {"symbol": "AAA", "positionAmt": "0"},
            {"symbol": "BBB", "qty": "1.5"},
        ]
    }
    assert parse_open_position_symbols(raw) == {"BBB"}
