.PHONY: help up down dev migrate test lint format seed

help:
	@echo "Comandos disponibles:"
	@echo "  make up       - Levanta todos los servicios (Docker)"
	@echo "  make down     - Para todos los servicios"
	@echo "  make dev      - Arranca el servidor en modo desarrollo"
	@echo "  make migrate  - Aplica las migraciones de base de datos"
	@echo "  make test     - Ejecuta los tests"
	@echo "  make lint     - Verifica el estilo del código"
	@echo "  make format   - Formatea el código automáticamente"
	@echo "  make seed     - Carga datos de ejemplo"

up:
	docker-compose up -d

down:
	docker-compose down

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	celery -A app.celery_app worker --loglevel=info --concurrency=4

beat:
	celery -A app.celery_app beat --loglevel=info

migrate:
	alembic upgrade head

migrate-create:
	alembic revision --autogenerate -m "$(name)"

migrate-down:
	alembic downgrade -1

test:
	pytest tests/ -v --asyncio-mode=auto --tb=short

test-cov:
	pytest tests/ -v --asyncio-mode=auto --cov=app --cov-report=html --cov-report=term-missing

lint:
	ruff check app/ tests/
	mypy app/ --ignore-missing-imports

format:
	ruff format app/ tests/
	ruff check --fix app/ tests/

seed:
	python scripts/seed.py

shell:
	python -c "import asyncio; from app.database import AsyncSessionLocal; asyncio.run(main())"

logs:
	docker-compose logs -f api
