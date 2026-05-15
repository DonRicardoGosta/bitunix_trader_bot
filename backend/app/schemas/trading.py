"""Trading API sémák."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderRequest(BaseModel):
    """Új rendelés feladás bemenet.

    Az opcionális ``tp_price`` / ``sl_price`` mezőkkel a Bitunix natívan
    rögzíti a take profit / stop loss triggert a belépő rendelésre.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    symbol: str = Field(..., examples=["BTCUSDT"])
    side: Literal["BUY", "SELL"]
    # Bitunix kötelező mező hedge módban is: új pozíció = OPEN, zárás = CLOSE (+ positionId).
    trade_side: Literal["OPEN", "CLOSE"] = Field(default="OPEN", alias="tradeSide")
    position_id: str | None = Field(
        default=None,
        alias="positionId",
        description="Kötelező tradeSide=CLOSE esetén a Bitunix API szerint.",
    )
    order_type: Literal["MARKET", "LIMIT"] = Field(..., alias="orderType")
    quantity: Decimal = Field(..., gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    leverage: int = Field(default=1, ge=1, le=125)
    reduce_only: bool = Field(default=False, alias="reduceOnly")
    client_order_id: str | None = Field(default=None, alias="clientOrderId")
    tp_price: Decimal | None = Field(default=None, gt=0, alias="tpPrice")
    sl_price: Decimal | None = Field(default=None, gt=0, alias="slPrice")
    tp_stop_type: Literal["MARK_PRICE", "LAST_PRICE"] = Field(
        default="MARK_PRICE", alias="tpStopType"
    )
    sl_stop_type: Literal["MARK_PRICE", "LAST_PRICE"] = Field(
        default="MARK_PRICE", alias="slStopType"
    )

    @model_validator(mode="after")
    def _close_requires_position_id(self) -> OrderRequest:
        if self.trade_side == "CLOSE" and not self.position_id:
            raise ValueError("positionId kötelező, ha tradeSide=CLOSE (Bitunix API).")
        return self


class OrderResponse(BaseModel):
    """Rendelés válasz a kliensnek."""

    client_order_id: str
    bitunix_order_id: str | None = None
    status: str
    dry_run: bool = False
    raw: dict | None = None


class PositionInfo(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    leverage: int


class TickerInfo(BaseModel):
    symbol: str
    last_price: Decimal
    high_24h: Decimal | None = None
    low_24h: Decimal | None = None
    volume_24h: Decimal | None = None
