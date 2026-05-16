"""SQLAlchemy ORM modellek.

A séma minimalista, de bővíthető: rendelések, pozíció pillanatképek,
ár tickerek, audit események és stratégia futás-naplók. A Bitunix maga
is forrás, a DB elsősorban authoritatív audit log és visszamenőleges elemzés.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import (
    Enum as SQLEnum,
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


class AuditLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class StrategyRunStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    NO_OP = "NO_OP"
    FAILED = "FAILED"


class CalibrationStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Order(Base, TimestampMixin):
    """Rendelés audit napló (a Bitunix saját rendelés-ID-jával társítva)."""

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_strategy_symbol_ts", "strategy_name", "symbol", "created_at"),
    )

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
    strategy_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    entry_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)


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


class AuditEvent(Base):
    """Strukturált, DB-be írt eseménynapló.

    Ez **az** authoritatív log: nincs külön fájl / stdout-only log a futási
    események számára. Az ``event`` egy dot-notation kulcs (pl.
    ``strategy.top_movers.signal``), a ``payload`` szabad JSON adat.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_event_ts", "event", "created_at"),
        Index("ix_audit_events_level_ts", "level", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[AuditLevel] = mapped_column(
        SQLEnum(AuditLevel, name="audit_level"),
        default=AuditLevel.INFO,
    )
    event: Mapped[str] = mapped_column(String(128))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    strategy_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )


class TpSlCalibration(Base):
    """TP/SL paraméterek óránkénti automatikus belövése.

    Egy rekord = egy kalibrációs futtatás. A ``summary`` JSON tartalmazza
    a globális mediánokat és a per-symbol célmozgás-százalékokat
    (raw price move %, leverage-független). A stratégia ezekből számolja
    a konkrét trigger árakat a belépéskor.

    A trading akkor "engedélyezett", ha legalább egy SUCCESS rekord van,
    aminek a ``finished_at``-je nem öregebb mint a kalibrációs intervallum
    kétszerese (default: 2 óra).
    """

    __tablename__ = "tpsl_calibrations"
    __table_args__ = (Index("ix_tpsl_calibrations_status_ts", "status", "finished_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[CalibrationStatus] = mapped_column(
        SQLEnum(CalibrationStatus, name="calibration_status"),
        default=CalibrationStatus.RUNNING,
    )
    triggered_by: Mapped[str] = mapped_column(String(32), default="scheduler")
    lookback_minutes: Mapped[int] = mapped_column(default=120)
    top_n: Mapped[int] = mapped_column(default=20)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class AppRuntimeSetting(Base):
    """Runtime felülírások (UI / operátor) — env alapértelmezés felett."""

    __tablename__ = "app_runtime_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class StrategyRun(Base):
    """Egy stratégia futás audit rekordja."""

    __tablename__ = "strategy_runs"
    __table_args__ = (
        Index("ix_strategy_runs_name_ts", "strategy_name", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[StrategyRunStatus] = mapped_column(
        SQLEnum(StrategyRunStatus, name="strategy_run_status"),
        default=StrategyRunStatus.RUNNING,
    )
    triggered_by: Mapped[str] = mapped_column(
        String(32), default="scheduler"
    )
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
