# Database rules

## Стек

- **PostgreSQL** поднимается через Docker Compose.
- **SQLAlchemy 2.0 async-стек**: `AsyncSession`, `async_sessionmaker`, `create_async_engine`. Драйвер — `psycopg` (psycopg3, поддерживает async нативно).
- **Любое обращение к БД — `async def` + `await`**. Никакого синхронного `Session.execute(...)` — только `await session.execute(...)`.
- Repository-методы все `async def`. Service-методы все `async def`. Handler'ы FastAPI — `async def` + `await service.method()`.

## Миграции

- Любое изменение схемы базы требует Alembic migration. Без исключений.
- Нельзя менять структуру таблиц без миграции (даже если «локально работает»).
- Все миграции должны быть воспроизводимыми (запускать в чистой БД на любой машине должны давать тот же результат).
- Разрешено использовать `alembic revision --autogenerate`, но миграцию **обязательно проверить глазами**: autogenerate иногда добавляет `op.drop_*` для нетронутых колонок или ошибается с типами.
- Алембик у нас работает в **async-режиме** — `alembic/env.py` запускает миграции через `asyncio.run(run_migrations_online())` с `async_engine_from_config`.

## Repository pattern

- Сервис не лезет в `AsyncSession` напрямую — только через `LinkRepository`.
- Repository принимает `AsyncSession` в `__init__`.
- Все методы repository — `async def` + `await session.execute(...)` / `await session.get(...)` / `await session.commit()`.
- `expire_on_commit=False` в `async_sessionmaker` — иначе после commit любое обращение к атрибуту триггерит refresh, что в async требует await и легко ломается.

## Что проверять

- Все изменения в БД-логике покрываются integration tests с реальной PostgreSQL (не SQLite-in-memory).
- Integration tests используют autouse-фикстуру очистки таблиц через `await session.execute(text("DELETE FROM links"))`.
