"""Kockázat / tőkeméretezés segédfüggvények.

Itt él a "margin = max(1% × futures egyenleg, 0.25 USDT)" számítás és
a mennyiség (qty) levezetése a margin × leverage / ár képletből.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from app.schemas.trading import ORDER_REQUEST_MAX_LEVERAGE


def effective_order_leverage(max_leverage: int) -> int:
    """Tőzsdei max leverage → ``OrderRequest``-kompatibilis érték (1…125).

    A Bitunix ``trading_pairs`` válaszban egyes pároknál ``maxLeverage`` > 125
    (pl. 200); a belső séma és API clamp miatt a stratégiák ezt itt vágják le.
    """
    pair_max = max(1, int(max_leverage))
    return min(pair_max, ORDER_REQUEST_MAX_LEVERAGE)


def compute_margin(
    available_balance: Decimal,
    *,
    pct_of_balance: Decimal = Decimal("0.01"),
    minimum_usdt: Decimal = Decimal("0.25"),
) -> Decimal:
    """Pozícióra szánt margin USDT-ben.

    A felhasználói specifikáció: a futures wallet egyenlegének 1%-a,
    de minimum 0.25 USDT.

    Negatív / nulla egyenleg esetén a minimumot adja vissza (a hívó eldönti,
    hogy ezzel mit kezd – tipikusan SKIP).

    Args:
        available_balance: Aktuális szabad USDT egyenleg.
        pct_of_balance: Részesedés (alap: 0.01 = 1%).
        minimum_usdt: Padló érték (alap: 0.25 USDT).
    """
    pct_part = (available_balance * pct_of_balance) if available_balance > 0 else Decimal(0)
    return max(pct_part, minimum_usdt)


def compute_quantity(
    *,
    margin_usdt: Decimal,
    leverage: int,
    price: Decimal,
    base_precision: int = 4,
) -> Decimal:
    """A pozíció mennyiségét adja vissza precízióra kerekítve.

    qty = (margin × leverage) / price, lefelé kerekítve a precízióra
    (sosem akarunk a marginnál többet kockáztatni a kerekítés miatt).

    Args:
        margin_usdt: Pozícióra szánt margin USDT-ben.
        leverage: Tőkeáttétel (egész szám).
        price: Az aktuális ár.
        base_precision: Mennyiség tizedeshelyek száma a szimbólumhoz.
    """
    if price <= 0:
        raise ValueError("price must be positive")
    if leverage <= 0:
        raise ValueError("leverage must be positive")
    raw = (margin_usdt * Decimal(leverage)) / price
    quant = Decimal(10) ** -int(base_precision)
    return raw.quantize(quant, rounding=ROUND_DOWN)
