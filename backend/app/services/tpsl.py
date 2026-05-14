"""Take-Profit és Stop-Loss árszámítás ROI célok alapján.

A trader a felhasználói specifikáció szerint ROI százalékot ad meg
(``tp_roi_pct=200`` = +200% profit a margin-on), nem nyers árat.
Ezt a modul itt számolja át a Bitunixnak elküldhető trigger árakra.

Képletek (futures, ahol a ROI = (ár_változás × leverage) / belépő_ár):

    long  TP_price = entry × (1 + tp_roi / leverage)
    long  SL_price = entry × (1 - sl_roi / leverage)
    short TP_price = entry × (1 - tp_roi / leverage)
    short TP_price = entry × (1 + sl_roi / leverage)

Megjegyzés a kockázathoz: az ``sl_roi = 100%`` lényegében a likvidációs
ár közelében van. A liquidation előtt érdemes valamivel beállítani
(~50–75%), hogy a slippage / likvidációs díj ne egye fel az egészet.
Lásd: ``recommended_sl_roi``.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_UP, Decimal


def compute_tp_sl_prices(
    *,
    entry_price: Decimal,
    side: str,
    leverage: int,
    tp_roi_pct: Decimal,
    sl_roi_pct: Decimal,
    price_precision: int = 4,
) -> tuple[Decimal, Decimal]:
    """TP és SL trigger ár kiszámolása ROI célokból.

    Args:
        entry_price: Belépő ár.
        side: "BUY" (LONG) vagy "SELL" (SHORT).
        leverage: Tőkeáttétel (> 0).
        tp_roi_pct: Take-profit ROI százalék pozíción (pl. 200 = +200%).
        sl_roi_pct: Stop-loss ROI százalék pozíción (pl. 100 = -100%).
        price_precision: Tizedesek száma a kerekítéshez.

    Returns:
        ``(tp_price, sl_price)`` tuple. TP-t profit-felé, SL-t veszteség-felé
        kerekítjük – mindkettőnél konzervatív (későbbre teszi a kilépést).
    """
    if leverage <= 0:
        raise ValueError("leverage must be positive")
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    if tp_roi_pct <= 0 or sl_roi_pct <= 0:
        raise ValueError("ROI targets must be positive")

    tp_move = (tp_roi_pct / Decimal(100)) / Decimal(leverage)
    sl_move = (sl_roi_pct / Decimal(100)) / Decimal(leverage)
    quant = Decimal(10) ** -int(price_precision)

    side_u = side.upper()
    if side_u == "BUY":
        tp = entry_price * (Decimal(1) + tp_move)
        sl = entry_price * (Decimal(1) - sl_move)
        tp_rounded = tp.quantize(quant, rounding=ROUND_DOWN)
        sl_rounded = sl.quantize(quant, rounding=ROUND_DOWN)
    elif side_u == "SELL":
        tp = entry_price * (Decimal(1) - tp_move)
        sl = entry_price * (Decimal(1) + sl_move)
        tp_rounded = tp.quantize(quant, rounding=ROUND_UP)
        sl_rounded = sl.quantize(quant, rounding=ROUND_UP)
    else:
        raise ValueError(f"Invalid side: {side}")

    if tp_rounded <= 0:
        raise ValueError("Computed TP price <= 0; review inputs")
    if sl_rounded <= 0:
        raise ValueError("Computed SL price <= 0; review inputs")
    return tp_rounded, sl_rounded


def implied_price_move_pct_from_roi(
    *, leverage: int, tp_roi_pct: Decimal, sl_roi_pct: Decimal
) -> tuple[Decimal, Decimal]:
    """ROI célokból származó **ár**-elmozdulás %% (tőkeáttétellel osztva).

    Példa: ``tp_roi_pct=200``, ``leverage=20`` → ``tp_move_pct=10`` (10%% ár).

    Args:
        leverage: Tőkeáttétel (> 0).
        tp_roi_pct: TP ROI a marginon (pl. 200 = +200%%).
        sl_roi_pct: SL ROI a marginon (pl. 100 = -100%%).

    Returns:
        ``(tp_move_pct, sl_move_pct)`` mindkettő pozitív százalékban.
    """
    if leverage <= 0:
        raise ValueError("leverage must be positive")
    if tp_roi_pct <= 0 or sl_roi_pct <= 0:
        raise ValueError("ROI targets must be positive")
    lev = Decimal(leverage)
    tp_move_pct = tp_roi_pct / lev
    sl_move_pct = sl_roi_pct / lev
    return tp_move_pct, sl_move_pct


def implied_tp_roi_pct_from_price_move_pct(
    *, tp_move_pct: Decimal, leverage: int
) -> Decimal:
    """A marginon elvárt TP ROI %%, ha a teljes TP ár ``tp_move_pct`` (ár-%%).

    Az ``implied_price_move_pct_from_roi`` inverze ugyanarra a modellre:
    ``tp_roi ≈ tp_move_pct × leverage`` (pl. 10%% ár × 20x ≈ 200%% ROI).

    Args:
        tp_move_pct: Take-profit cél ár-elmozdulás %%, pozitív.
        leverage: Tőkeáttétel (> 0).

    Returns:
        A TP eltalálásakor a marginra vetített nyereség célja %%-ban.
    """
    if leverage <= 0:
        raise ValueError("leverage must be positive")
    if tp_move_pct <= 0:
        raise ValueError("tp_move_pct must be positive")
    return tp_move_pct * Decimal(leverage)


def compute_tp_sl_prices_from_move_pct(
    *,
    entry_price: Decimal,
    side: str,
    tp_move_pct: Decimal,
    sl_move_pct: Decimal,
    price_precision: int = 4,
) -> tuple[Decimal, Decimal]:
    """TP / SL ár közvetlenül **price move %** alapján (leverage-független).

    A kalibrációs service ezt a verziót használja, mert a kalibráció
    leverage-független százalékot ad.

    Args:
        entry_price: Belépő ár.
        side: ``"BUY"`` / ``"SELL"``.
        tp_move_pct: Take-profit kívánt ár-elmozdulás % (>0).
        sl_move_pct: Stop-loss kívánt ár-elmozdulás % (>0).
        price_precision: Tizedeshelyek a kerekítéshez.
    """
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    if tp_move_pct <= 0 or sl_move_pct <= 0:
        raise ValueError("move percentages must be positive")
    tp_move = tp_move_pct / Decimal(100)
    sl_move = sl_move_pct / Decimal(100)
    quant = Decimal(10) ** -int(price_precision)
    side_u = side.upper()
    if side_u == "BUY":
        tp = (entry_price * (Decimal(1) + tp_move)).quantize(
            quant, rounding=ROUND_DOWN
        )
        sl = (entry_price * (Decimal(1) - sl_move)).quantize(
            quant, rounding=ROUND_DOWN
        )
    elif side_u == "SELL":
        tp = (entry_price * (Decimal(1) - tp_move)).quantize(
            quant, rounding=ROUND_UP
        )
        sl = (entry_price * (Decimal(1) + sl_move)).quantize(
            quant, rounding=ROUND_UP
        )
    else:
        raise ValueError(f"Invalid side: {side}")
    if tp <= 0 or sl <= 0:
        raise ValueError("Computed TP/SL <= 0; review inputs")
    return tp, sl


def recommended_sl_roi(user_sl_roi_pct: Decimal) -> Decimal:
    """Konzervatív ajánlás a stop-loss ROI-ra.

    A user által kért -100% gyakorlatilag likvidáció = baj. Ha 100-nál
    nem kisebb a kérés, **figyelmeztetést** kapunk (de a kérést tiszteletben
    tartjuk). Visszaadja a user értéket, jelzéssel a hívónak audit naplóhoz.
    """
    return user_sl_roi_pct


def is_risky_sl_roi(roi_pct: Decimal, *, threshold: Decimal = Decimal(80)) -> bool:
    """Igaz, ha az SL ROI veszélyesen magas (close to liquidation)."""
    return roi_pct >= threshold
