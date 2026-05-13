"""Plugable stratégia keretrendszer.

A stratégiák itt vannak regisztrálva, és a ``StrategyRunner`` időzítve futtatja
őket. Egy új stratégia hozzáadása:

1. Hozd létre az osztályt ``Strategy``-ből származtatva.
2. Regisztráld a ``registry.STRATEGIES`` dict-be.
3. (Opcionálisan) Bővítsd a ``Settings``-et a saját kapcsolóiddal.
"""

from app.services.strategy.base import Strategy, StrategyContext, StrategyResult
from app.services.strategy.registry import (
    STRATEGIES,
    StrategyNotFoundError,
    available_strategies,
    get_strategy,
)
from app.services.strategy.runner import StrategyRunner, run_strategy

__all__ = [
    "STRATEGIES",
    "Strategy",
    "StrategyContext",
    "StrategyResult",
    "StrategyRunner",
    "StrategyNotFoundError",
    "available_strategies",
    "get_strategy",
    "run_strategy",
]
