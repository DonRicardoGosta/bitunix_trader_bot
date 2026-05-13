# Bitunix Trader

> **Magyar dokumentáció lent. English documentation below.**
>
> Egy minimalista, de teljes körű **Bitunix Futures** kereskedő alkalmazás:
> FastAPI backend + Next.js frontend + PostgreSQL, mind Dockerben.
>
> Cursor-stílusú projektfelépítés (`.cursor/rules/`, `AGENTS.md`),
> kétnyelvű dokumentáció, tesztek backend + frontend oldalon egyaránt.

---

## 🇭🇺 Magyar

### 📦 Mi van a dobozban?

| Komponens   | Technológia                                               | Port |
| ----------- | --------------------------------------------------------- | ---- |
| `db`        | PostgreSQL 16 (Alpine)                                    | 5432 |
| `backend`   | FastAPI · SQLAlchemy 2 async · Alembic · httpx · websockets · pluggable stratégia framework | 8000 |
| `frontend`  | Next.js 14 (App Router) · TypeScript · TailwindCSS        | 3000 |

A backend a Bitunix REST + WebSocket API-jával kommunikál, kezelve az aláírást
(dupla SHA256), a rendelés audit logot a Postgresben, és egy "dry-run" módot,
amelyben az alkalmazás **soha nem küld** élő rendelést.

### 🚀 Indítás 3 lépésben

```bash
# 1. Másold és töltsd ki az env fájlt:
cp .env.example .env
#   Szerkeszd a BITUNIX_API_KEY és BITUNIX_API_SECRET mezőket.
#   Élesre csak akkor állítsd a BITUNIX_LIVE_TRADING=true-ra, ha biztos vagy
#   benne, hogy minden teszt zöld és tudatában vagy a kockázatoknak.

# 2. Build és indítás:
make build
make up

# 3. Migrációk lefuttatása (a backend ezt automatikusan is megteszi indításkor):
make migrate
```

Elérhetőség:

* Frontend: <http://localhost:3000>
* API docs (Swagger UI): <http://localhost:8000/docs>
* API health: <http://localhost:8000/api/health>

### 🛡 Biztonsági kapcsolók

| Változó                              | Alap            | Hatás                                                   |
| ------------------------------------ | --------------- | ------------------------------------------------------- |
| `BITUNIX_LIVE_TRADING`                     | `false`             | Ha `false`, semmilyen rendelés nem megy a Bitunixhoz.            |
| `STRATEGY_RUNNER_ENABLED`                  | `false`             | A háttér scheduler kapcsolója.                                   |
| `STRATEGY_INTERVAL_SECONDS`                | `300`               | Két lefutás közti idő.                                           |
| `STRATEGY_TOP_MOVERS_COOLDOWN_MINUTES`     | `240`               | Per-szimbólum cooldown a `top_movers` stratégiához.              |
| `STRATEGY_TOP_MOVERS_DIRECTION_MODE`       | `momentum_breakout` | `trend` \| `momentum_breakout` \| `mean_revert`                  |
| `STRATEGY_TOP_MOVERS_RANGE_THRESHOLD`      | `0.66`              | Momentum_breakout küszöb a 24h tartomány felső/alsó zónájához.   |
| `STRATEGY_MARGIN_PCT_OF_BALANCE`           | `0.01`              | Margin arány a futures egyenlegből (1%).                         |
| `STRATEGY_MIN_MARGIN_USDT`                 | `0.25`              | Margin padló.                                                    |
| `STRATEGY_TP_ROI_PCT`                      | `200`               | TP ROI fallback (ha nincs friss kalibráció).                     |
| `STRATEGY_SL_ROI_PCT`                      | `100`               | SL ROI fallback (likvidáció-közeli, lásd alábbi javaslat).       |
| `STRATEGY_TPSL_STOP_TYPE`                  | `MARK_PRICE`        | `MARK_PRICE` vagy `LAST_PRICE` – Bitunix trigger típus.          |
| `CALIBRATION_ENABLED`                      | `true`              | TP/SL kalibrációs scheduler kapcsoló.                            |
| `CALIBRATION_INTERVAL_SECONDS`             | `3600`              | Két kalibrációs futás között eltelő idő.                         |
| `CALIBRATION_LOOKBACK_MINUTES`             | `120`               | Visszanéző ablak (2 óra) ATR számításhoz.                        |
| `CALIBRATION_TOP_N`                        | `20`                | Hány top szimbólumra fusson le.                                  |
| `CALIBRATION_TP_ATR_MULT` / `_SL_ATR_MULT` | `3.0` / `1.5`       | ATR multiplikátorok → TP/SL price move % (R:R = 2:1).            |
| `REQUIRE_CALIBRATION_FOR_TRADING`          | `true`              | Ha igaz, tradelés csak friss SIKERES kalibráció után.            |
| `DB_CPU_LIMIT` / `DB_MEM_LIMIT`            | `1.0` / `512M`      | Docker erőforrás-korlát a Postgresre.                            |
| `BACKEND_CPU_LIMIT` / `BACKEND_MEM_LIMIT`  | `1.0` / `512M`      | Docker korlát a backendre.                                       |
| `FRONTEND_CPU_LIMIT` / `FRONTEND_MEM_LIMIT`| `1.0` / `1G`        | Docker korlát a frontendre.                                      |
| `APP_ENV`                                  | `development`       | `production` esetén szigorúbb defaultok.                         |
| `BACKEND_CORS_ORIGINS`                     | localhost:3000      | Engedélyezett CORS originek.                                     |

**Soha** ne add ki a `BITUNIX_API_SECRET`-et és **soha** ne kommitold az
`.env` fájlt. A `.gitignore` ezt eleve kizárja.

### 🤖 Stratégiák

A stratégia keretrendszer pluggable: a regisztrált logikák a
`backend/app/services/strategy/` alatt élnek. Minden stratégia futás
és minden döntés a DB-be kerül – **nincs külön log csatorna**, az
`audit_events` tábla az egyetlen authoritatív napló.

**`top_movers` stratégia** (alapból elérhető):

1. Lekérdezi az összes szimbólum 24h tickerét (`GET /futures/market/tickers`).
2. Rangsorolja őket **|24h % változás|** csökkenő sorrendben (az esések is játszanak).
3. Veszi a **top 3**-at.
4. Szimbólumonként ellenőrzi a **4 órás cooldownt** (per-stratégia, per-szimbólum).
5. **Irány** (configurálható, `STRATEGY_TOP_MOVERS_DIRECTION_MODE`):
   * `momentum_breakout` (**alapértelmezett, ajánlott**): pozitív 24h változás
     **és** ár a 24h tartomány felső harmadában → LONG. Negatív változás
     **és** ár az alsó harmadban → SHORT. Egyébként **skip** (kétértelmű
     mozgás, valószínűleg konszolidál vagy fordul).
   * `trend`: tisztán a 24h változás előjele dönt.
   * `mean_revert`: ellenirány (a "túlfutott" mozgás visszafelé fade-elése).
6. Lekéri a `maxLeverage`-ét (`GET /futures/market/trading_pairs`), és
   **beállítja** (`POST /futures/account/change_leverage`).
7. Margin: `max(1% × futures USDT egyenleg, 0.25 USDT)`.
8. **TP / SL** trigger árak kiszámolva ROI-célokból, atomi módon az entry
   order-rel **egyetlen REST hívásban** (a Bitunix `place_order` támogatja a
   `tpPrice` és `slPrice` paramétereket). Lásd `app/services/tpsl.py`.

### ⚠️ Javaslat a TP/SL beállításra

A felhasználói specifikáció szerint a default `TP_ROI=200%` és `SL_ROI=100%`.
Az SL ROI=100% **gyakorlatilag a likvidációs árszint**. Ez kockázatos, mert:
* A likvidáció előtti néhány tickben a slippage könnyen "túlszalad" az SL-en,
* A tőzsde likvidációs díja is felemésztheti a maradékot,
* Egy "wick" (rövid ártranziens) is kiviheti, miközben nincs hova kilépni.

Konzervatívabb és tipikusan **profitabilisebb** elrendezés:

| Paraméter        | User spec | Ajánlott          |
| ---------------- | --------- | ----------------- |
| `STRATEGY_TP_ROI_PCT` | `200` | `100`–`200`       |
| `STRATEGY_SL_ROI_PCT` | `100` | `50`–`75`         |
| R:R arány        | 2:1       | 2:1–4:1           |

A backend `WARNING` szintű audit eseményt ír a `audit_events` táblába minden
futás elején, ha az SL ROI ≥ 80% (`strategy.top_movers.risky_sl_warning`).

### 🎯 TP/SL automatikus belövés (kalibráció)

A `top_movers` stratégia **per-szimbólum kalibrált TP/SL targeteket** is
használ, ami felülírja a fenti ROI defaulteket. A kalibrációs process az
**app indulásakor azonnal lefut**, majd **óránként** újra. Trading csak
akkor engedélyezett, ha létezik friss, sikeres kalibráció.

**Mit csinál a kalibrációs runner:**
1. Lekéri a top 20 szimbólumot (`|24h % változás|` alapján).
2. Mindegyikre lekér **2 órányi 1-perces gyertyát** (= 120 minta).
3. Kiszámolja az **ATR**-t a closing ár százalékában (recent realized
   volatility).
4. `tp_move% = ATR × 3.0` és `sl_move% = ATR × 1.5` → **R:R = 2:1**, ami
   matematikailag pozitív várt érték már ~40% hit rate-nél is.
5. Plafon / padló: `CALIBRATION_MIN_/MAX_TP_/SL_MOVE_PCT` korlátok között.
6. Per-symbol és globális mediánt is tárol – ha a stratégia egy olyan
   coint választ, ami nem volt a top 20-ban, a globális mediánt használja.

**Endpointok:**
* `GET /api/calibration/latest` – aktuális állapot, `trading_enabled` flag
* `GET /api/calibration/runs` – futási történet
* `POST /api/calibration/run` – kézi indítás (háttér task)

A `Kalibráció` UI oldal mutatja a status badge-et, a globális TP/SL
targeteket, a per-szimbólum tábláját, és a futási történetet. A dashboardon
egy banner jelzi ha a trading **le van tiltva**.

Indítás:
* API: `POST /api/strategies/top_movers/run` (manuális)
* Scheduler: `STRATEGY_RUNNER_ENABLED=true` (5 percenként, vagy ahogy beállítod)
* UI: a **Stratégiák** oldalon `Indítás most` gomb

A teljes audit látható a **Eseménynapló** oldalon, vagy
`GET /api/events?strategy_name=top_movers&level=INFO`.

### 🧱 Projekt fa

```
.
├── .cursor/rules/         # Cursor agent szabályok
├── AGENTS.md              # útmutató AI agenteknek
├── .env.example           # környezeti változók sablon
├── docker-compose.yml     # három szolgáltatás
├── Makefile               # fejlesztői parancsok
├── backend/
│   ├── app/
│   │   ├── api/routes/    # /health /market /orders /positions /account
│   │   ├── bitunix/       # REST kliens + aláírás + WS
│   │   ├── db/            # SQLAlchemy modellek, session
│   │   ├── schemas/       # Pydantic DTO-k
│   │   ├── services/      # üzleti logika
│   │   ├── config.py      # Pydantic settings
│   │   └── main.py        # FastAPI factory
│   │   ├── api/routes/    # /health /market /orders /positions /account
│   │   │                  # /strategies /events
│   │   ├── services/strategy/   # stratégia framework (base, registry, runner)
│   │   │                        # + top_movers stratégia
│   │   └── db/audit.py    # authoritatív DB-be írt eseménynapló
│   ├── alembic/           # DB migrációk (3 revision)
│   ├── tests/             # pytest (64 teszt)
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/           # Next.js App Router (dashboard, trade, orders,
│   │   │                  #   positions, strategies, events)
│   │   ├── components/    # üzleti komponensek + UI primitívek
│   │   └── lib/           # API kliens, segédfüggvények
│   ├── tests              # Vitest (21 teszt) — komponensek mellett
│   └── package.json
└── ARCHITECTURE.md        # részletes architektúra
```

### 🧪 Tesztelés

```bash
make test            # backend + frontend
make test-backend    # csak pytest
make test-frontend   # csak Vitest
make lint            # ruff + eslint
```

A tesztek nem igényelnek Bitunix kapcsolatot – minden hálózati hívás
mockolva van (`respx` / `fetch` mock), és a dry-run mód miatt egyébként sem
megy ki valódi kérés.

### 🛠 Fejlesztés Docker nélkül

Ha a Docker stack helyett nyersen szeretnél futtatni:

```bash
# Backend
cd backend
virtualenv .venv && source .venv/bin/activate
pip install -e ".[dev]" aiosqlite
DATABASE_URL=postgresql+asyncpg://trader:trader@localhost:5432/bitunix_trader \
  alembic upgrade head
uvicorn app.main:app --reload

# Frontend egy másik terminálban:
cd frontend
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

### 🔌 Bitunix integráció részletek

A REST kliens (`backend/app/bitunix/client.py`) a hivatalos algoritmussal
ír alá: `SHA256(SHA256(nonce + timestamp + api_key + query + body) + secret)`.
A `query` paraméterek ASCII rendezett `kulcsÉrtékkulcsÉrtek` formátumban, a
`body` JSON whitespace nélkül. Részletek a
[hivatalos dokumentációban](https://www.bitunix.com/api-docs/futures/common/sign.html).

A WebSocket kliens (`backend/app/bitunix/ws.py`) automatikus újrakapcsolódást
és ping-keepalive-ot kezel a publikus csatornákhoz (`wss://fapi.bitunix.com/public/`).

### 📚 További olvasnivalók

* [`ARCHITECTURE.md`](./ARCHITECTURE.md) – rétegek, adatfolyam, döntések
* [`AGENTS.md`](./AGENTS.md) – AI agentek számára
* [`backend/README.md`](./backend/README.md) – backend specifikus
* [`frontend/README.md`](./frontend/README.md) – frontend specifikus

### ❓ Megjegyzés a UI keretrendszerről

Az eredeti megrendelés "liaui"-t említett, ami nem azonosítható ismert UI
keretrendszerként. Az iparági legjobb gyakorlatok mentén egy modern stacket
választottam (Next.js + TailwindCSS + shadcn-stílusú primitívek a
`frontend/src/components/ui/` alatt). Ha más eszközt szerettél volna (pl.
shadcn/ui, DaisyUI, Mantine), nyiss egy issue-t és cseréljük le.

### ⚠️ Disclaimer

Ez egy **oktatási / kiindulási** projekt. A futures kereskedés magas
kockázatú, könnyen elveszítheted a teljes befektetésedet. **A szerző nem
vállal felelősséget** semmilyen pénzügyi veszteségért. Mindig kis tőkével
és testnet/dry-run módban teszteld.

---

## 🇬🇧 English

A minimalist but complete **Bitunix Futures** trading app:
FastAPI backend + Next.js frontend + PostgreSQL, all dockerized.

### Quick start

```bash
cp .env.example .env       # fill BITUNIX_API_KEY / BITUNIX_API_SECRET
make build
make up
make migrate
```

* Frontend: <http://localhost:3000>
* API docs: <http://localhost:8000/docs>

### Safety

`BITUNIX_LIVE_TRADING=false` (the default) means **no real orders** are sent –
everything is logged to Postgres and replayed as a dry-run response. Flip to
`true` only when you have validated everything and accept the risks.

### Testing

```bash
make test          # backend (pytest) + frontend (Vitest)
make lint          # ruff + eslint
```

### Layout

```
backend/   FastAPI app  (auth + REST client + WS + Alembic migrations + tests)
frontend/  Next.js app  (dashboard + trade + orders + positions + Vitest tests)
docker-compose.yml, Makefile, .env.example, AGENTS.md, .cursor/rules/
```

### Note on the UI framework

The original Hungarian request mentioned `liaui` which I could not identify
as a known library. I went with Next.js + TailwindCSS + shadcn-style
primitives. Swap if you wanted something else.

### Disclaimer

Educational project. Futures trading is risky – use at your own risk.
