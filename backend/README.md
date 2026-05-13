# Backend - Bitunix Trader

FastAPI alapú backend a Bitunix Futures kereskedéshez.

## Modulok

| Modul                     | Szerep                                          |
| ------------------------- | ----------------------------------------------- |
| `app/main.py`             | FastAPI alkalmazás összeállítása, routing       |
| `app/config.py`           | Pydantic settings – környezeti változók         |
| `app/db/`                 | SQLAlchemy session, modellek                    |
| `app/bitunix/`            | Bitunix REST + WS kliens, aláírás logika        |
| `app/services/`           | Üzleti logika (trading, market data)            |
| `app/api/routes/`         | HTTP routerek                                   |
| `app/schemas/`            | Pydantic kérés/válasz sémák                     |
| `alembic/`                | DB migrációk                                    |
| `tests/`                  | pytest tesztek                                  |

## Lokális futtatás Docker nélkül

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL=postgresql+asyncpg://trader:trader@localhost:5432/bitunix_trader
alembic upgrade head
uvicorn app.main:app --reload
```

API dokumentáció: <http://localhost:8000/docs>
