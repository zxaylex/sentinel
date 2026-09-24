.PHONY: dev test lint format migrate migration seed up down

dev:
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

up:
	docker compose up -d

down:
	docker compose down -v

test:
	uv run pytest -v

lint:
	uv run ruff check . && uv run mypy app/

format:
	uv run ruff format .

migrate:
	uv run alembic upgrade head

migration:
	uv run alembic revision --autogenerate -m "$(msg)"

seed:
	uv run python -m app.seeds.run
