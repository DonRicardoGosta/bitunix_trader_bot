"""Stratégia regisztri."""

from __future__ import annotations

from app.services.strategy.base import Strategy
from app.services.strategy.top_movers import TopMoversStrategy


class StrategyNotFoundError(LookupError):
    """Adott név nincs regisztrálva."""


STRATEGIES: dict[str, type[Strategy]] = {
    TopMoversStrategy.name: TopMoversStrategy,
}


def available_strategies() -> list[str]:
    return sorted(STRATEGIES.keys())


def get_strategy(name: str) -> Strategy:
    """Egy név alapján példányosított stratégiát ad vissza."""
    cls = STRATEGIES.get(name)
    if cls is None:
        raise StrategyNotFoundError(name)
    return cls()
