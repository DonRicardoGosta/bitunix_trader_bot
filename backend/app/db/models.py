"""SQLAlchemy ORM modellek.

A séma minimalista, de bővíthető: rendelések, pozíció pillanatképek,
ár tickerek és audit naplók kerülnek tárolásra. A Bitunix maga is forrás,
a DB elsősorban gyorsítótár, audit log és visszamenőleges elemzés.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    NEW = "NEW"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class Order(Base, TimestampMixin):
    """Rendelés audit napló (a Bitunix saját rendelés-ID-jával társítva)."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    bitunix_order_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[OrderSide] = mapped_column(SQLEnum(OrderSide, name="order_side"))
    type: Mapped[OrderType] = mapped_column(SQLEnum(OrderType, name="order_type"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    price: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    leverage: Mapped[int] = mapped_column(default=1)
    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(OrderStatus, name="order_status"),
        default=OrderStatus.NEW,
        index=True,
    )
    reduce_only: Mapped[bool] = mapped_column(default=False)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)


class PositionSnapshot(Base, TimestampMixin):
    """Időbeli pozíció pillanatkép (PnL elemzéshez)."""

    __tablename__ = "position_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[OrderSide] = mapped_column(SQLEnum(OrderSide, name="order_side"))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    mark_price: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    leverage: Mapped[int] = mapped_column(default=1)


class MarketTick(Base):
    """Nyers piaci tick (ár + volumen)."""

    __tablename__ = "market_ticks"
    __table_args__ = (Index("ix_market_ticks_symbol_ts", "symbol", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    price: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
