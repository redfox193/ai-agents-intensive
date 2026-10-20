---
name: tests-integration
description: >
  Пишет интеграционные тесты полного пути HTTP → API → Service → Repository → БД:
  AsyncTestClient, реальная тестовая БД, проверка кодов ответов и состояния БД.
owner: tbd
freedom: guided
last_reviewed: 2026-07-13
---

# Skill: Integration Tests

## Когда применять

Проверка полного пути запроса через реальные слои и БД. Изолированная бизнес-логика —
`tests-unit.md`; фронтенд — `tests-frontend.md`; стратегия для эпиков —
`tests-strategy.md`.

## Входной контракт

| Вход | Формат / где взять | Нет → действие |
|---|---|---|
| Acceptance criteria эндпоинта | PRD (FR-ID) / T-задача / data contracts из architecture-doc | ASK — без AC тест фиксирует текущее поведение, не спеку |
| API-контракт: метод, путь, схемы, коды | architecture-doc «Data contracts» или роутер | вывести из контракта, НЕ из тела хендлера |
| Тестовая БД | PostgreSQL в Docker | поднять; нет возможности — ASK, не мокать БД |

**Правило слепоты:** тесты пишутся от API-контракта и AC, не от чтения реализации
хендлера. Для новых эндпоинтов: тест по контракту (красный) → потом реализация.

## Алгоритм написания integration тестов

### 1. Подготовка
- Прочитать `.agents/agents/testing.md` и `.agents/agents/database.md`.
- Integration тесты проверяют **полный путь**: HTTP-запрос → API → Service → Repository → PostgreSQL.
- **Проект полностью async**: handler'ы async, сервис async, репозиторий async, `AsyncSession` через DI.

### 2. Структура
- Файлы: `tests/integration/test_<endpoint>.py`.
- HTTP-клиент: **`AsyncTestClient`** из `litestar.testing` (он async и поддерживает `async with`). Старый sync-`TestClient` тоже работает (внутри сам крутит event loop), но `AsyncTestClient` чище для async-проекта.
- Реальная тестовая БД (PostgreSQL в Docker).
- **autouse-фикстура очистки таблицы — async**, выполняется через `async with SessionLocal() as session: await session.execute(text("DELETE FROM links"))`.

### 3. Правила
- Только `pytest`, функции. Никакого `unittest.TestCase`.
- **Все тестовые функции `async def`** — `asyncio_mode = "auto"` в `pyproject.toml` запустит их без `@pytest.mark.asyncio`.
- **autouse-фикстура очистки — тоже `async`**:
  ```python
  @pytest.fixture(autouse=True)
  async def clean_db() -> AsyncGenerator[None, None]:
      async with SessionLocal() as session:
          await session.execute(text("DELETE FROM links"))
          await session.commit()
      yield
      async with SessionLocal() as session:
          await session.execute(text("DELETE FROM links"))
          await session.commit()
```
- **TestClient вызывается через `async with`** или через создание клиента в фикстуре. **`follow_redirects=False`** обязателен — нам нужно проверить именно 302 и `Location`, а не финальный ответ.
- Не зависеть от порядка выполнения тестов.
- Аннотации `-> None` у каждой тестовой функции, `async def`.
- `from __future__ import annotations` первой строкой файла.

### Пример теста (async + AsyncTestClient)

```python
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from litestar.testing import AsyncTestClient
from sqlalchemy import text

from app.db.session import SessionLocal
from app.main import app


@pytest.fixture(autouse=True)
async def clean_db() -> AsyncGenerator[None, None]:
    async with SessionLocal() as session:
        await session.execute(text("DELETE FROM links"))
        await session.commit()
    yield
    async with SessionLocal() as session:
        await session.execute(text("DELETE FROM links"))
        await session.commit()


async def test_post_link_returns_201() -> None:
    async with AsyncTestClient(app=app, follow_redirects=False) as client:
        response = await client.post("/links/", json={"url": "https://example.com"})
        assert response.status_code == 201
        body = response.json()
        assert body["code"]
        assert body["original_url"] == "https://example.com"
        assert body["clicks"] == 0
```

### 4. Что тестировать

**Не только happy path.** На каждый эндпоинт должны быть тесты для трёх категорий:

- **Happy path** — валидный запрос → ожидаемый успех (200/201, корректное тело JSON, данные в БД).
- **Граничные случаи (boundary)** — значения **на краю** допустимого диапазона. Например для URL длиной 2048 (максимум) — должен принять; для URL длиной 2049 — должен отказать. Boundary-тесты ловят off-by-one ошибки.
- **Невалидный ввод** — что возвращает API на пустой URL, на `"not-a-url"`, на missing-field, на slash в конце, на превышение лимитов. Ожидаем 422 (а не 500). На несуществующий ресурс — 404.

Плюс при багфиксе — **regression test** на конкретную проблему (см. `.skills/bugfix.md`).

Конкретные пункты:

- Все HTTP-методы эндпоинта (GET, POST, PUT/PATCH, DELETE).
- Коды ответов (200, 201, 404, 422) — все ветки, не только успешная.
- Тело ответа — структура JSON, проверять конкретные поля (`assert body["code"]`, не только `body is not None`).
- Что данные реально сохраняются/удаляются в БД (через `await session.execute(select(...))` после запроса).
- Заголовки ответа когда они важны (Location на 302-редиректе, Content-Type на JSON-ответе).

### 5. Проверка
- `uv run ruff format .` — автоформатирование.
- `uv run ruff check --fix .` — автофикс автофиксимых правил.
- `uv run ruff check .` — должно быть зелёно.
- `uv run basedpyright`
- `uv run pytest tests/integration/ -q` — все тесты зелёные, без warnings про event loop или sync-в-async.
- Ориентир объёма: ≤ 5–6 тестов на acceptance criterion; в docstring — какой AC/FR-ID
  проверяется.
- Для нового эндпоинта: показать red → green (тест падал до реализации).

## Эскалация

- **ASK:** AC/контракт эндпоинта отсутствует или противоречив; тест требует данных/
  доступов, которых нет; подозрение на баг в чужом коде (тест ловит, но задача не о нём).
- **NEVER (решает только человек):** `skip`/`xfail` существующих тестов; мок БД вместо
  реальной тестовой; снижение порогов; правка AC «под тест»; удаление чужого
  падающего теста.

## Анти-паттерны

- ❌ Тест по телу хендлера («что делает — то и ждём») → ✅ по API-контракту и AC
- ❌ Проверка только кода ответа без тела и состояния БД → ✅ код + JSON-поля + `select` в БД
- ❌ Общие данные между тестами (зависимость от порядка) → ✅ autouse-очистка, изоляция
- ❌ Boundary blindness: только явный invalid-input → ✅ границы диапазонов (2048/2049)
- ❌ Тавтологичные assert (`body is not None`) → ✅ конкретные поля и значения из AC
