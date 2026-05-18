# =============================================================================
# Bitunix Trader - fejlesztői Makefile / Developer Makefile
# =============================================================================
# Használat / Usage:
#   make help       - parancslista / list commands
#   make up         - docker stack indítása / start docker stack
#   make down       - leállítás / stop
#   make logs       - log követés / follow logs
#   make test       - összes teszt / all tests
# =============================================================================

.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help
help: ## Parancsok listája / List commands
	@awk 'BEGIN {FS = ":.*##"; printf "\nElérhető parancsok / Available commands:\n"} \
		/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ---- Docker stack ----------------------------------------------------------
.PHONY: build up down restart logs ps
build: ## Image-ek építése / Build images
	$(COMPOSE) build

up: ## Stack indítása háttérben / Start stack detached
	$(COMPOSE) up -d

down: ## Stack leállítása / Stop stack
	$(COMPOSE) down

restart: down up ## Újraindítás / Restart

logs: ## Log követés / Follow logs
	$(COMPOSE) logs -f --tail=100

ps: ## Konténer állapot / Container status
	$(COMPOSE) ps

# ---- Adatbázis / Database --------------------------------------------------
.PHONY: migrate makemigration db-shell
migrate: ## Alembic migrációk futtatása / Run alembic migrations
	$(COMPOSE) run --rm backend alembic upgrade head

makemigration: ## Új migráció (msg="..." kötelező) / New migration
	$(COMPOSE) run --rm backend alembic revision --autogenerate -m "$(msg)"

db-shell: ## psql shell a db konténerbe / psql shell into db
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-trader} -d $${POSTGRES_DB:-bitunix_trader}

# ---- Tesztek / Tests -------------------------------------------------------
.PHONY: test test-backend test-frontend lint
test: test-backend test-frontend ## Összes teszt / Run all tests

test-backend: ## Backend pytest
	$(COMPOSE) run --rm backend pytest -v

test-frontend: ## Frontend Vitest
	$(COMPOSE) run --rm frontend npm run test -- --run

lint: ## Lint mindkét oldalon / Lint both sides
	$(COMPOSE) run --rm backend ruff check .
	$(COMPOSE) run --rm frontend npm run lint

# ---- Helyi fejlesztés (Docker nélkül) / Local dev (no docker) --------------
.PHONY: dev-backend dev-frontend
dev-backend: ## Backend lokálisan / Backend locally
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## Frontend lokálisan / Frontend locally
	cd frontend && npm run dev

.PHONY: frontend-clean
frontend-clean: ## Next.js cache törlése (ChunkLoadError után) / Clear .next cache
	$(COMPOSE) exec frontend sh -c "rm -rf .next" 2>/dev/null || rm -rf frontend/.next
	@echo "frontend/.next törölve — futtasd: make restart"
