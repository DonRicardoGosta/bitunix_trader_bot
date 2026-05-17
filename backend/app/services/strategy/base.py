"""Stratégia bázis ABC + kontextus DTO-k."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.bitunix.client import BitunixClient
from app.config import Settings
from app.schemas.strategy_config import TopSignalEntriesConfig


@dataclass
class StrategyContext:
    """Egy stratégia futás bemeneti kontextusa."""

    session: AsyncSession
    client: BitunixClient
    settings: Settings
    top_signal_entries: TopSignalEntriesConfig
    triggered_by: str = "scheduler"


@dataclass
class StrategyResult:
    """Egy stratégia futás kimenete (jelek, rendelések, döntések)."""

    placed_orders: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_no_op(self) -> bool:
        return not self.placed_orders


class Strategy(ABC):
    """Stratégia bázis interfész.

    A konkrét osztály ``name``-mel és ``run`` koroutinnal rendelkezik.
    """

    name: str = "abstract"

    @abstractmethod
    async def run(self, ctx: StrategyContext) -> StrategyResult:
        """Egy lefutás. A hívó (``StrategyRunner``) feleli a fel- és
        leiratkozást a Bitunix klienssel, valamint a session commit-ját.
        """
