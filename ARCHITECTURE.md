# Architektúra / Architecture

> Részletes nézet a Bitunix Trader rétegeiről, adatáramlásáról és tervezési döntéseiről.

## 1. Magas szintű kép

```
┌────────────────────┐        HTTP/JSON         ┌────────────────────┐
│   Next.js frontend │ ───────────────────────▶│   FastAPI backend  │
│   (Browser, :3000) │ ◀───── SSE / poll ───── │      (:8000)       │
└────────────────────┘                          └─────────┬──────────┘
                                                          │
                                       async SQLAlchemy   │   httpx / websockets
                                                          ▼
                                          ┌────────────────────────────┐
                                          │   PostgreSQL (:5432)        │
                                          │   audit log, snapshots      │
                                          └────────────────────────────┘
                                                          ▲
                                                          │
                                                          ▼
                                          ┌────────────────────────────┐
                                          │   Bitunix Futures API       │
                                          │   REST: fapi.bitunix.com    │
                                          │   WS:   /public, /private   │
                                          └────────────────────────────┘
```

## 2. Backend rétegek

```
HTTP request
   │
   ▼
api/routes/*.py        ◀── FastAPI router + Pydantic séma validáció
   │
   ▼
services/*.py          ◀── üzleti logika (DB + Bitunix komponálva)
   │            │
   │            └──▶ bitunix/client.py    ◀── REST hívások, dupla SHA256 aláírás
   │            └──▶ bitunix/ws.py        ◀── WS reconnect + ping
   ▼
db/models.py + session.py  ◀── async SQLAlchemy 2
```

### Miért FastAPI?

* Aszinkron végpontok natívan: a Bitunix REST + WS hívások I/O kötöttek.
* OpenAPI dokumentáció ingyen → a frontend könnyen generálhat klienst.
* Pydantic v2 = gyors validáció + szigorú típusok.

### Miért külön `services/` és `bitunix/` réteg?

* A `services/` ismeri a DB-t és a Bitunixot is, és audit logot vezet.
* A `bitunix/` izolált kliens – cserélhető, tesztelhető respx-szel.
* A `routes/` csak HTTP-fordítás, üzleti logikát nem tartalmaz.

## 3. Aláírás (Bitunix Futures REST)

A teljes algoritmust az `app/bitunix/auth.py` valósítja meg, és külön unit
tesztek validálják a hivatalos példák alapján (`tests/test_signature.py`).

```
nonce      = 32 char random hex
timestamp  = current unix time in ms
queryParams= sorted key+value concatenation (key1value1key2value2)
body       = JSON without spaces

digest = SHA256(nonce + timestamp + api_key + queryParams + body)
sign   = SHA256(digest + secretKey)
```

A header set: `api-key`, `nonce`, `timestamp`, `sign`, `Content-Type`.

## 4. Adatmodellek

```
orders                       audit_events              strategy_runs
  id                           id                        id
  client_order_id*             level (DEBUG..ERROR)      strategy_name
  bitunix_order_id             event (dot.notation)      status (RUNNING|SUCCESS|
  symbol                       message                          NO_OP|FAILED)
  side  (BUY/SELL)             payload  (JSON)           triggered_by
  type  (MARKET/LIMIT)         strategy_name             details  (JSON)
  quantity                     created_at                error
  price                                                  started_at / finished_at
  leverage
  status
  reduce_only             position_snapshots         market_ticks
  raw_response  (JSON)      id                         id
  strategy_name             symbol, side               symbol, price
  created_at / updated_at   entry/mark price           volume, created_at
                            qty, unrealized_pnl
                            leverage
```

* `orders` – authoritatív audit log a saját rendelésekről. A `strategy_name`
  oszlop alapján szűr a cooldown logika.
* `audit_events` – **az** authoritatív futási napló (nincs külön log fájl
  vagy stdout-only csatorna a business eseményekhez).
* `strategy_runs` – egy-egy stratégia futás kimenete (időbélyegekkel és
  szerkezet-független `details` JSON-nel).

## 5. Frontend

* **App Router** – minden oldal `src/app/<útvonal>/page.tsx`.
* **Komponens primitívek** `src/components/ui/` alatt (`Button`, `Card`,
  `Input`, `Label`, `Select`) – shadcn ihletésű, Tailwind alapú.
* **Üzleti komponensek** `src/components/` (Navbar, OrderForm, MarketTicker,
  OrdersTable).
* **API kliens** `src/lib/api.ts` – a backenddel beszél, **soha nem** közvetlenül
  a Bitunixszal (a kulcsok csak a backenden élnek).

## 6. Tesztpiramis

| Réteg                       | Eszköz                       | Példa                         |
| --------------------------- | ---------------------------- | ----------------------------- |
| Tiszta függvények           | pytest / vitest              | `test_signature.py`, `utils.test.ts` |
| Komponens / endpoint        | TestClient / RTL             | `test_orders_endpoint.py`, `OrderForm.test.tsx` |
| Integráció (Bitunix mock)   | respx (backend), fetch mock  | `OrderForm.test.tsx`          |
| End-to-end (manuális)       | docker compose + böngésző    | dev folyamat része            |

## 7. Stratégia framework

```
                       ┌─────────────────────────────┐
                       │       StrategyRunner        │
                       │  (asyncio scheduler loop)   │
                       └──────────────┬──────────────┘
                                      │ every N seconds
                                      ▼
                       ┌─────────────────────────────┐
                       │      run_strategy(name)     │
                       │   (creates StrategyRun row) │
                       └──────────────┬──────────────┘
                                      │
                                      ▼
                       ┌─────────────────────────────┐
                       │ Strategy.run(ctx)           │
                       │   ctx: session, client,     │
                       │        settings             │
                       └──────┬─────────────┬────────┘
                              │             │
                  audit.record()        BitunixClient
                       writes              REST/WS
                       events
                       to DB
```

A `Strategy` ABC interfész minimális: `name` + `async run(ctx) -> StrategyResult`.
A `registry.STRATEGIES` dict tartalmazza a regisztrált osztályokat – új
stratégia ide kerül berakásra.

### `TopSignalEntriesStrategy` döntéslánc

```
GET /futures/market/tickers       ─┐
GET /futures/market/trading_pairs  ─┤  (párhuzamos)
GET /futures/account?marginCoin=USDT ┘
            │
            ▼  rank_top_movers (mover_ranking, abs % csökkenő, top N)
            │
            ▼  kline fetch (első lookahead jelölt) + entry_side_from_mover_and_klines
            │  opcionális WF gate → TP/SL a variációból
            │
            ▼  cooldown check: orders.strategy_name='top_signal_entries'
            │
            ▼  change_leverage → margin/qty → TP/SL (kalibráció / ROI)
            │
            ▼  TradingService.place_order(... tpPrice, slPrice)
                  └── audit.record('strategy.top_signal_entries.order_placed', ...)
```

### Miért az "atomi TP/SL"?

A Bitunix `place_order` endpoint támogatja `tpPrice` és `slPrice` paramétereket
(`POST /api/v1/futures/trade/place_order`), így **egyetlen REST hívásban** megy
a entry order és a TP/SL trigger. A Bitunix dokumentáció szerint a **`tradeSide`**
(`OPEN` / `CLOSE`) kötelező; a tőkeáttétel **nem** a place_order törzsében megy,
hanem előtte a `change_leverage` végponton. Ezzel:
- Nem fordulhat elő, hogy a entry order beteljesül, de a TP/SL beállítása
  hálózati hiba miatt elmarad.
- Nem kell külön a `positionId`-t lekérdezni, ami egy második körkérés lenne.

## 8. Biztonsági réteg

1. **Dry-run alapérték** – `BITUNIX_LIVE_TRADING=false` mellett nem megy ki
   valódi rendelés. A switch fizikailag egyetlen helyen szóródik szét
   (`BitunixClient.place_order` / `cancel_order`).
2. **Titkok nem logolódnak** – a `BitunixClient` soha nem írja ki a secretet,
   és a hibák `BitunixAPIError`-on át terjednek a routerig, ahol állapotkóddá
   konvertálódnak.
3. **CORS whitelist** – `BACKEND_CORS_ORIGINS` env változóból.
4. **Frontend nem ismeri a kulcsot** – minden Bitunix hívás a backenden át.

## 9. Bővítési pontok

* **TradingView chart** beilleszthető a `frontend/src/app/trade/page.tsx`-be.
* **Stratégia worker** új modulként a `backend/app/services/strategy.py` alatt,
  külön taskként futtatva (pl. Celery / APScheduler).
* **Privát WS csatorna** – a `bitunix/ws.py` kibővíthető login üzenettel és
  a `/private` URL-lel, hogy a pozíció-update real-time érkezzen.
* **Risk engine** – ár-eltérési / pozíció-méret limit ellenőrzés a
  `services/trading.py`-ban a `place_order` előtt.

## 10. Tervezési kompromisszumok

| Döntés                                        | Miért?                                                    |
| --------------------------------------------- | --------------------------------------------------------- |
| Async SQLAlchemy 2 + asyncpg                  | A teljes I/O stack async, nincs blokkoló szál.            |
| Alembic migrációk (nem `create_all`)          | Termelési séma változás követhetősége.                    |
| Pydantic v2                                   | 5–20× gyorsabb mint v1, jobb DX.                          |
| Tailwind + shadcn-stílus (nem külső csomag)   | Minimális függőség, teljes kontroll a komponensek felett. |
| TanStack Query opcionálisan (most useEffect)  | A scaffold egyszerű marad; bővíthető cache/staleTime-mal. |
| Postgres az SQLite helyett éles módban        | Számszerű precízió (NUMERIC 28,12), konkurrens írás.      |
