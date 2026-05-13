"""Bitunix Futures REST kliens (aszinkron, httpx-alapú).

Csak a leggyakoribb műveleteket implementálja kiindulásként – a teljes
végpont-listát később egyszerű kibővíteni a Bitunix dokumentációja alapján.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx

from app.bitunix.auth import build_auth_headers
from app.bitunix.exceptions import BitunixAPIError, BitunixSignatureError


class BitunixClient:
    """Aszinkron HTTP kliens a Bitunix Futures REST API-hoz.

    Példa:
        >>> async with BitunixClient(api_key="...", api_secret="...") as c:
        ...     await c.get_ticker("BTCUSDT")
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        base_url: str = "https://fapi.bitunix.com",
        timeout: float = 10.0,
        live_trading: bool = False,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = base_url.rstrip("/")
        self._live_trading = live_trading
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    async def __aenter__(self) -> BitunixClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    # -- public végpontok --------------------------------------------------

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Aktuális ticker egy szimbólumhoz (public, nincs aláírás)."""
        return await self._request(
            "GET",
            "/api/v1/futures/market/tickers",
            params={"symbols": symbol},
            authenticated=False,
        )

    async def get_all_tickers(self) -> dict[str, Any]:
        """Összes szimbólum 24h tickere (``symbols`` paraméter nélkül).

        A válasz ``data`` mezője egy lista, elemenként:
        ``{symbol, lastPrice, open, high, low, baseVol, quoteVol, markPrice, ...}``
        """
        return await self._request(
            "GET",
            "/api/v1/futures/market/tickers",
            authenticated=False,
        )

    async def get_trading_pairs(self) -> dict[str, Any]:
        """Kereskedési párok metaadatai (precíziók, min/max leverage)."""
        return await self._request(
            "GET",
            "/api/v1/futures/market/trading_pairs",
            authenticated=False,
        )

    async def get_depth(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        """Orderbook depth lekérdezés."""
        return await self._request(
            "GET",
            "/api/v1/futures/market/depth",
            params={"symbol": symbol, "limit": limit},
            authenticated=False,
        )

    async def get_klines(
        self,
        symbol: str,
        *,
        interval: str = "1m",
        limit: int = 200,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        kline_type: str = "LAST_PRICE",
    ) -> dict[str, Any]:
        """Kline (gyertyák) lekérdezés egy szimbólumra.

        Args:
            symbol: pl. ``"BTCUSDT"``.
            interval: ``1m``, ``5m``, ``15m``, ``30m``, ``1h``, ``2h``, ``4h``,
                ``6h``, ``8h``, ``12h``, ``1d``, ``3d``, ``1w``, ``1M``.
            limit: max 200.
            start_time_ms / end_time_ms: opcionális szűrés (Unix ms).
            kline_type: ``LAST_PRICE`` vagy ``MARK_PRICE``.
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(max(1, limit), 200),
            "type": kline_type,
        }
        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)
        return await self._request(
            "GET",
            "/api/v1/futures/market/kline",
            params=params,
            authenticated=False,
        )

    # -- privát végpontok --------------------------------------------------

    async def get_account(self, margin_coin: str = "USDT") -> dict[str, Any]:
        """Számla információ (egyenlegek, marginok).

        Args:
            margin_coin: Pl. ``"USDT"`` (a futures wallet base coinja).
        """
        return await self._request(
            "GET",
            "/api/v1/futures/account",
            params={"marginCoin": margin_coin},
            authenticated=True,
        )

    async def change_leverage(
        self,
        *,
        symbol: str,
        leverage: int,
        margin_coin: str = "USDT",
    ) -> dict[str, Any]:
        """Tőkeáttétel beállítása egy szimbólumra.

        ``BITUNIX_LIVE_TRADING=false`` esetén dry-run választ ad.
        """
        body = {
            "symbol": symbol,
            "leverage": int(leverage),
            "marginCoin": margin_coin,
        }
        if not self._live_trading:
            return {"dryRun": True, "echo": body}
        return await self._request(
            "POST",
            "/api/v1/futures/account/change_leverage",
            json=body,
            authenticated=True,
        )

    async def get_positions(self, symbol: str | None = None) -> dict[str, Any]:
        """Nyitott pozíciók lekérdezése."""
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        return await self._request(
            "GET",
            "/api/v1/futures/position/get_pending_positions",
            params=params or None,
            authenticated=True,
        )

    async def place_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal | str,
        price: Decimal | str | None = None,
        leverage: int = 1,
        reduce_only: bool = False,
        client_order_id: str | None = None,
        tp_price: Decimal | str | None = None,
        sl_price: Decimal | str | None = None,
        tp_stop_type: str = "MARK_PRICE",
        sl_stop_type: str = "MARK_PRICE",
    ) -> dict[str, Any]:
        """Rendelés feladása (opcionális natív TP/SL-lel).

        A Bitunix ``/futures/trade/place_order`` egyetlen hívással elfogadja
        a ``tpPrice`` / ``slPrice`` paramétereket, így az entry order és a
        TP/SL triggerek atomi módon, együtt mennek ki.

        Ha ``live_trading=False``, a kliens NEM küld igazi rendelést,
        csak naplóz és visszaad egy "dry-run" választ.
        """
        body: dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "orderType": order_type.upper(),
            "qty": str(quantity),
            "leverage": leverage,
            "reduceOnly": reduce_only,
        }
        if price is not None:
            body["price"] = str(price)
        if client_order_id:
            body["clientId"] = client_order_id
        if tp_price is not None:
            body["tpPrice"] = str(tp_price)
            body["tpStopType"] = tp_stop_type
            body["tpOrderType"] = "MARKET"
        if sl_price is not None:
            body["slPrice"] = str(sl_price)
            body["slStopType"] = sl_stop_type
            body["slOrderType"] = "MARKET"

        if not self._live_trading:
            return {
                "dryRun": True,
                "echo": body,
                "note": "BITUNIX_LIVE_TRADING=false – nincs valódi rendelésküldés.",
            }

        return await self._request(
            "POST",
            "/api/v1/futures/trade/place_order",
            json=body,
            authenticated=True,
        )

    async def cancel_order(
        self, *, symbol: str, order_id: str
    ) -> dict[str, Any]:
        """Rendelés visszavonása."""
        if not self._live_trading:
            return {"dryRun": True, "echo": {"symbol": symbol, "orderId": order_id}}

        return await self._request(
            "POST",
            "/api/v1/futures/trade/cancel_orders",
            json={"symbol": symbol, "orderList": [{"orderId": order_id}]},
            authenticated=True,
        )

    # -- belső segédek -----------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        authenticated: bool = False,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if authenticated:
            if not (self._api_key and self._api_secret):
                raise BitunixSignatureError(
                    "Bitunix API kulcs/secret hiányzik a konfigurációból."
                )
            headers = build_auth_headers(
                api_key=self._api_key,
                secret_key=self._api_secret,
                query=params,
                body=json,
            )

        try:
            response = await self._client.request(
                method, path, params=params, json=json, headers=headers
            )
        except httpx.HTTPError as exc:
            raise BitunixAPIError(f"HTTP hiba: {exc}") from exc

        if response.status_code >= 400:
            raise BitunixAPIError(
                f"Bitunix {response.status_code}: {response.text}",
                status_code=response.status_code,
            )

        data = response.json()
        if isinstance(data, dict) and data.get("code") not in (None, 0, "0", "00000"):
            raise BitunixAPIError(
                data.get("msg") or "Bitunix üzleti hiba",
                code=str(data.get("code")),
            )
        return data
