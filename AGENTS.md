# AGENTS.md

Útmutató AI ügynököknek (Cursor, Claude Code, Codex stb.) a **Bitunix Trader** projekthez.

> Tipp: ez a fájl a `.cursor/rules/` szabályrendszer kiegészítője, és minden agent automatikusan olvassa.

## A projekt egy mondatban
Egy Bitunix Futures piacon kereskedő webalkalmazás: FastAPI backend + Next.js frontend + PostgreSQL, mind Dockerben.

## Gyors hivatkozások
| Mit keresel?            | Hol van                                       |
| ----------------------- | --------------------------------------------- |
| API routerek            | `backend/app/api/routes/`                     |
| Bitunix REST/WS kliens  | `backend/app/bitunix/`                        |
| DB modellek             | `backend/app/db/models.py`                    |
| Alembic migrációk       | `backend/alembic/versions/`                   |
| Üzleti logika           | `backend/app/services/`                       |
| UI komponensek          | `frontend/src/components/`                    |
| Next.js oldalak         | `frontend/src/app/`                           |
| Környezeti változók     | `.env.example`                                |
| Docker stack            | `docker-compose.yml`                          |

## Indítás (zero-to-running)
```bash
cp .env.example .env       # töltsd ki a BITUNIX_API_* mezőket
make build                 # image-ek build
make up                    # stack indítása
make migrate               # DB migrációk
# UI:  http://localhost:3000
# API: http://localhost:8000/docs
```

## Tesztelés
- `make test` – minden teszt (backend pytest + frontend Vitest)
- `make test-backend` / `make test-frontend` – részhalmaz
- Új feature → új teszt. Aláírási logikához mindig hivatalos dokumentum-példára épülő unit teszt.

## Fontos szabályok ügynököknek
1. **Soha** ne kommitold az `.env` fájlt vagy bármilyen API kulcsot.
2. **Soha** ne küldj élő rendelést Bitunixra teszt során – ehhez `BITUNIX_LIVE_TRADING=true` kell és kézi jóváhagyás.
3. DB séma változás → Alembic revision (`make makemigration msg="..."`).
4. Új környezeti változó → frissítsd a `.env.example`-t **és** a `docker-compose.yml`-t.
5. **Nincs külön log csatorna** – minden business esemény DB-be megy az
   `app.db.audit.record()` / `record_isolated()` segítségével. Stdout csak a
   startup banner. Ne add vissza a `structlog`-ot a service rétegbe.
6. A felhasználó kommunikáció nyelve magyar, a kódé angol.
7. Commit konvenció: `type(scope): leírás`.

## Tipikus feladatok recept-szerűen
### Új API endpoint
1. Hozz létre routert `backend/app/api/routes/<terület>.py` alatt.
2. Pydantic kérés/válasz sémák `backend/app/schemas/<terület>.py`.
3. Üzleti logika `backend/app/services/`.
4. Regisztráld a routert `backend/app/main.py`-ban.
5. Írj tesztet `backend/tests/test_<terület>.py`.

### Új UI oldal
1. `frontend/src/app/<útvonal>/page.tsx`.
2. Komponens(ek) `frontend/src/components/`.
3. API hívás `frontend/src/lib/api.ts`-ben definiált függvénnyel.
4. Vitest teszt mellé.

### Új stratégia
1. Hozz létre osztályt `backend/app/services/strategy/<név>.py` alatt,
   `Strategy`-ből származtatva. `name` property + `async run(ctx)`.
2. Regisztráld a `registry.STRATEGIES` dict-be.
3. Új konfig env-eket (`STRATEGY_<NÉV>_*`) tegyél be a `Settings`-be,
   `.env.example`-be és `docker-compose.yml`-be.
4. Az audit hívásokhoz használd `app.db.audit.record()`-ot a kontextus
   sessionjével, hogy a stratégia tranzakcióval együtt commit-oljon.
5. Cooldown / state derived a `orders` táblából (`strategy_name` oszlop).
6. Tesztek: tiszta logika unit tesztek (rangsorolás, számítás), majd egy
   integráció a `FakeBitunixClient` mintával (`tests/test_top_movers_strategy.py`).
