"""Top movers stratégia tiszta funkcionális tesztek (kliens nélkül).

A ``_rank_top_movers`` és ``_index_trading_pairs`` belső segédfüggvényeket
közvetlenül teszteljük, hogy a rangsorolás abszolút értékkel működjön és
a max leverage helyesen jöjjön ki a trading_pairs válaszból.
"""

from __future__ import annotations

from decimal import Decimal

from app.services.strategy.top_movers import (
    _extract_available_usdt,
    _index_trading_pairs,
    _rank_top_movers,
)


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
    top3 = _rank_top_movers(raw, top_n=3)
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
    top = _rank_top_movers(raw, top_n=10)
    assert [m.symbol for m in top] == ["AAA"]


def test_rank_top_movers_accepts_bare_list() -> None:
    """Néha a data eleve lista – mindkettő működjön."""
    raw = [
        {"symbol": "X", "lastPrice": "200", "open": "100"},
        {"symbol": "Y", "lastPrice": "50", "open": "100"},
    ]
    top = _rank_top_movers(raw, top_n=2)
    assert top[0].symbol == "X"
    assert abs(top[0].change_pct) >= abs(top[1].change_pct)


def test_index_trading_pairs_returns_max_leverage_per_symbol() -> None:
    raw = {
        "data": [
            {"symbol": "BTCUSDT", "maxLeverage": "125", "basePrecision": "3"},
            {"symbol": "ETHUSDT", "maxLeverage": "100", "basePrecision": "2"},
            {"symbol": "WEIRD"},  # hiányos – default 1x és 4 tizedes
        ]
    }
    index = _index_trading_pairs(raw)
    assert index["BTCUSDT"].max_leverage == 125
    assert index["BTCUSDT"].base_precision == 3
    assert index["ETHUSDT"].max_leverage == 100
    assert index["WEIRD"].max_leverage == 1
    assert index["WEIRD"].base_precision == 4


def test_extract_available_usdt_from_account_payload() -> None:
    raw = {"code": 0, "data": {"available": "123.45", "frozen": "1"}}
    assert _extract_available_usdt(raw) == Decimal("123.45")


def test_extract_available_usdt_empty() -> None:
    assert _extract_available_usdt({}) == Decimal("0")
    assert _extract_available_usdt({"data": {}}) == Decimal("0")
