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
| `backend`   | FastAPI · SQLAlchemy 2 async · Alembic · httpx · websockets | 8000 |
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

| Változó                   | Alap   | Hatás                                               |
| ------------------------- | ------ | --------------------------------------------------- |
| `BITUNIX_LIVE_TRADING`    | `false`| Ha `false`, semmilyen rendelés nem megy a Bitunixhoz – csak DB-be naplóz. |
| `APP_ENV`                 | `development` | `production` esetén JSON strukturált log, szigorúbb defaultok. |
| `BACKEND_CORS_ORIGINS`    | localhost:3000 | Engedélyezett CORS originek (vesszővel elválasztva). |

**Soha** ne add ki a `BITUNIX_API_SECRET`-et és **soha** ne kommitold az
`.env` fájlt. A `.gitignore` ezt eleve kizárja.

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
│   ├── alembic/           # DB migrációk
│   ├── tests/             # pytest (12 teszt)
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/           # Next.js App Router (dashboard, trade, orders, positions)
│   │   ├── components/    # üzleti komponensek + UI primitívek
│   │   └── lib/           # API kliens, segédfüggvények
│   ├── tests              # Vitest (13 teszt) — komponensek mellett
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
