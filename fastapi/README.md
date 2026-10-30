# День 1. Скилы и харнес: сокращатель ссылок на FastAPI

Каталог `fastapi/` на ветках `main` и `day-1` — стартовый проект первого дня интенсива Pytex
«От вайб-кодинга к профессиональной AI-разработке». В нём лежит **полное единое приложение**
сервиса коротких ссылок и **только 7 базовых скилов** одиночного инженера.

**Приложение едино для трёх дней и доступно с первого дня** (links + analytics + billing, все
маршруты).
Побайтово одинаковы во всех трёх днях шесть объектов приложения и окружения: `app/`, `alembic/`,
`alembic.ini`, `uv.lock`, `docker-compose.yml`, `.env.example`.
`pyproject.toml` един по зависимостям и настройкам инструментов и отличается только учебным порогом
покрытия `fail_under`: `50` в Дне 1 (лестница `50 → 60 → 80 → 85`) и `85` в Днях 2-3.
Каталог `tests/` (вместе с `agent-battle/`) даёт общую базу из 98 тестов приложения во всех трёх днях;
в Дне 3 к ней добавлены два файла тестов обвязки — `tests/unit/test_kb_sync.py` (со `snap-1`) и
`tests/unit/test_layer_linter_exhaustive.py` (со `snap-4`), всего 104 теста.
Дни различаются **скилами и обвязкой агента**: **7 → 9 → 15** скилов. Оркестрация (День 2:
конвейер, `.ai-team/`, `scripts/`) и приёмка монолита (День 3: `tools/`, `.planning/`, граф знаний)
здесь не лежат: они добавляются на ветках `day-2` и `day-3` соответственно.

- Проект всегда лежит в `fastapi/`: именно в него ведут команды из `ПРЕРЕКВИЗИТЫ.md`
  (`cd ~/work/Python-AI/fastapi`). Ветки `main` и `day-1` указывают на один и тот же коммит.
- Дни переключаются ветками: `git checkout day-1` (или `main`), `git checkout day-2`,
  `git checkout day-3` (в Дне 3 ещё `git checkout snap-0` … `snap-6`). Навигация по трём дням —
  в корневом [README.md](../README.md) репозитория.

## Скилы Дня 1 (`.agents/skills/`)

| Скил | Для чего |
| --- | --- |
| `investigate-codebase` | Читает код, строит карту слоёв и зону влияния правок; ничего не меняет |
| `characterization-tests` | Фиксирует текущее поведение эндпоинтов тестами до любых правок |
| `tests-unit` | Быстрые тесты бизнес-логики на Fake-репозитории, покрытие ветвлений |
| `tests-integration` | Сквозные тесты API и репозиториев с реальной PostgreSQL |
| `database-migration` | Обратимые миграции Alembic: upgrade, downgrade, повторный upgrade |
| `fastapi-feature` | Новая функциональность послойно: схемы, репозиторий, сервис, роутер |
| `safe-refactoring` | Рефакторинг и строгая типизация без изменения поведения |

Правила репозитория — [`.agents/AGENTS.md`](.agents/AGENTS.md); корневой `AGENTS.md`
отправляет агента туда и к скилам. Подробный сценарий дня — `Ранбук-День-1-Скилы-и-Харнес.md`.

## Назначение

Учебный backend на FastAPI для создания коротких ссылок. Сервис хранит ссылки в
PostgreSQL, поддерживает срок действия и пользовательский короткий код, считает
переходы, позволяет отключить и включить ссылку, ведёт аналитику кликов и биллинг.

Для URL назначения разрешены схемы `http` и `https`. Приложение отклоняет URL с
учётными данными, `localhost`, loopback-адресами, приватными и зарезервированными
IP-адресами. Проверка выполняется без DNS-разрешения имени.

## Быстрый старт

Понадобятся Python 3.14 или новее, [uv](https://docs.astral.sh/uv/) и Docker с
Compose.

```bash
cp .env.example .env
uv sync
docker compose up -d db
uv run alembic upgrade head
uv run fastapi dev app/main.py
```

Сервер разработки слушает `http://127.0.0.1:8000`. Создать ссылку можно так:

```bash
curl -X POST http://127.0.0.1:8000/links \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/page","ttl_seconds":3600,"custom_code":"docs2026"}'
```

В ответе поле `short_url` содержит адрес для перехода. Остановка базы:

```bash
docker compose down
```

Данные PostgreSQL остаются в Docker volume `pgdata`. Команда `docker compose down -v`
удалит volume вместе с данными.

## Конфигурация ENV

Настройки читаются из переменных окружения и файла `.env`. За образец можно взять
[`.env.example`](.env.example).

| Переменная | Значение по умолчанию | Назначение |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://app:app@localhost:5432/app` | URL подключения SQLAlchemy к PostgreSQL |
| `BASE_URL` | `http://127.0.0.1:8000` | Основа поля `short_url` в ответах API |
| `CODE_LENGTH` | `7` | Длина автоматически созданного кода, допустимы значения от 4 до 16 |
| `POSTGRES_PORT` | `5432` | Порт PostgreSQL на хосте, используется только в `docker-compose.yml` |

Если меняется `POSTGRES_PORT`, тот же порт нужно указать в `DATABASE_URL`. Остальные
переменные (`APP_ENV`, `DEBUG`, `PROJECT_NAME`, `API_V1_PREFIX`) перечислены в
[`.env.example`](.env.example) и описаны в `app/core/config.py`.

## Миграции

Alembic получает `DATABASE_URL` из той же конфигурации, что и приложение. Перед
запуском миграций база должна принимать подключения.

Применить все миграции:

```bash
uv run alembic upgrade head
```

Проверить текущую ревизию:

```bash
uv run alembic current
```

Создать миграцию после изменения ORM-моделей:

```bash
uv run alembic revision --autogenerate -m "описание изменения"
```

Откатить одну ревизию:

```bash
uv run alembic downgrade -1
```

Ревизии: `001_initial_links` (таблица `links`, уникальный индекс по `short_code`),
`002_add_analytics_events` (таблица `click_events`), `003_add_created_at_idx` (индекс по
`links.created_at`).

## Запуск

Режим разработки с автоматической перезагрузкой:

```bash
uv run fastapi dev app/main.py
```

Запуск без автоматической перезагрузки:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Compose запускает только PostgreSQL. Процесс приложения запускается отдельно одной
из команд выше.

## Тесты и проверки качества

Проверки качества проходят без изменения production-кода:

```bash
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest -q
```

Полный набор тестов приложения доступен с Дня 1 и проходит зелёным (SQLite в памяти, Postgres
для тестов не нужен): `tests/unit/` (сервисы, домен, биллинг), `tests/integration/` (API
`/api/v1/...`, биллинг), `tests/characterization/` (слепок поведения), `tests/flat_api/`
(плоские маршруты `/links` и `/{code}`), а также
[`agent-battle/repo/tests/agent_battle/test_atomic_clicks.py`](agent-battle/repo/tests/agent_battle/test_atomic_clicks.py)
(2 теста): атомарный счётчик переходов реализован в `LinkRepository.increment_clicks`
(`UPDATE links SET clicks = clicks + 1 WHERE short_code = :code RETURNING ...`), а
`LinkService.resolve` вызывает его вместо чтения-изменения-записи.

Порог покрытия в `pyproject.toml` стартует с `fail_under = 50` и поднимается по лестнице
скилов «только вверх»: `60` (`characterization-tests`) → `80` (`tests-integration`) → `85`
(`fastapi-feature`); на ветках `day-2` и `day-3` он уже равен `85`. Покрытие проверяется флагами
`--cov=app --cov-branch`.

Демонстрация гонки «до фикса» не входит в `pytest`: скрипт
[`agent-battle/race_demo.py`](agent-battle/race_demo.py) запускает 20 параллельных чтений-
изменений-записей (старая схема) и показывает потерянные клики, затем тот же сценарий с
атомарным инкрементом:

```bash
uv run python agent-battle/race_demo.py
```

Набор pre-commit-проверок включает Ruff, basedpyright, Bandit, `pip-audit`, проверку
lock-файла и поиск секретов:

```bash
uv run pre-commit run --all-files
```

Нагрузочный сценарий находится в [`locustfile.py`](locustfile.py). Для его запуска
нужен работающий API:

```bash
uv run locust --host http://127.0.0.1:8000
```

Интерфейс Locust будет доступен по адресу `http://127.0.0.1:8089`.

## Архитектура

Код разделён по слоям (`schemas → core → services → api`, обратные импорты запрещены):

```text
HTTP-запрос
  |
  +-- app/main.py, app/api   маршруты, зависимости, преобразование ошибок в HTTP-статусы
       |
       +-- app/services      сценарии: создание, редирект, отключение, аналитика, биллинг
            |
            +-- app/repositories  SQLAlchemy-запросы (только flush; commit — в `get_db()`)
                 |
                 +-- app/models, app/db   ORM-модели, async engine и сессии

app/schemas   Pydantic-контракты и SSRF-валидатор;  app/core   настройки, логирование, протоколы
app/domain    сущность Link, value objects, доменные ошибки (доменный сервис Дня 1)
```

[`app/main.py`](app/main.py) собирает FastAPI-приложение. Сессия БД создаётся на HTTP-запрос
(`app.db.session.get_db`) и делает commit после успешной обработки либо rollback при исключении.
Схема таблиц управляется миграциями из [`alembic/versions`](alembic/versions), настройки — в
[`app/core/config.py`](app/core/config.py) (`app/config.py` — фасад).

Пути из скилов существуют как тонкие модули поверх базовых: `app/core/security.py`
(`validate_target_url`, `generate_short_code`), `app/models/link.py`, `app/schemas/link.py`
(`LinkCreate`, `LinkRead`, `LinkStats`), `app/repositories/link.py`, `app/services/link.py`,
`app/api/v1/links.py` (алиас `app/api/v1/endpoints/links.py`), `app/api/routes.py`,
`app/db/models.py`. Доменный сервис Дня 1 (`app/services/link_service.py` с протоколом
репозитория и `app/repositories/link_repository.py`) не зависит от HTTP-слоя и нужен для
unit-тестов и `agent-battle/`; функциональные фасады `app/repo.py`, `app/service.py`,
`app/models_flat.py` сохраняют имена модулей Дня 2.

## API

| Метод | Путь | Результат |
| --- | --- | --- |
| `POST` | `/links` | `201`: `short_code`, `target_url`, `disabled` |
| `GET` | `/links` | До 100 последних ссылок (полные данные), новые первыми |
| `GET` | `/links/{short_code}` | Данные ссылки со счётчиком; `404` для отключённой и неизвестной |
| `POST` | `/links/{short_code}/disable`, `/enable` | `200`: `short_code`, `target_url`, `disabled`; `404` на неизвестный код |
| `GET` | `/{short_code}` | Увеличивает счётчик переходов и отвечает редиректом `307`; `404 Link disabled` / `404 Link not found`, `410` для истёкшей |
| `POST` | `/api/v1/links` | Создание: `201`, полные данные (`original_url`/`target_url`, `clicks`/`clicks_count`, `is_active`/`disabled`, `short_url`, `status`) |
| `POST` | `/api/v1/links/bulk` | Массовое создание в одной транзакции |
| `GET` | `/api/v1/links` | Список ссылок |
| `GET` | `/api/v1/links/{code}` | Счётчик переходов и редирект `307`; `404` — нет, `410` — отключена или истекла |
| `GET` | `/api/v1/links/{code}/stats` | Статистика: счётчик, статус, даты; `404` на неизвестный код |
| `POST` | `/api/v1/links/{code}/disable`, `/enable` | Управление активностью, ответ с `is_active` |
| `GET` | `/api/v1/analytics/{code}` | Аналитика кликов: всего, уникальные, источники |
| `POST` | `/billing/wallets/top-up`, `/billing/charges/click` | Пополнение и списание за клик (`402` при нехватке средств, идемпотентность по `transaction_id`) |
| `GET` | `/health` | Проверка живости |

Тело `POST /links` и `POST /api/v1/links`:

```json
{
  "url": "https://example.com/page",
  "ttl_seconds": 3600,
  "custom_code": "docs2026"
}
```

Обязательно только адрес назначения: поле `url` (допустимы синонимы `target_url` и
`original_url`). Положительный `ttl_seconds` (до года) задаёт срок действия в секундах;
ноль и отрицательное значение дают `422`. `custom_code` — от 3 до 16 символов
`[a-zA-Z0-9_-]`; без него сервис создаёт код сам. Конфликт кода — `409 Conflict`,
недопустимый URL или код — `422 Unprocessable Entity`.

Интерактивная документация после запуска:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI JSON: `http://127.0.0.1:8000/api/v1/openapi.json`

## Эксперимент: Вайб-кодинг против Скилов (`tools/toggle_skills.py`)

Для наглядного сравнения дикого вайб-кодинга и профессиональной разработки в репозиторий добавлена утилита переключения скилов:

```bash
cd ~/work/Python-AI/fastapi

# 1. Отключить скилы (режим чистого вайб-кодинга)
python3 tools/toggle_skills.py --disable

# 2. Проверить статус
python3 tools/toggle_skills.py --status   # -> 🔴 Скилы ОТКЛЮЧЕНЫ

# 3. Включить скилы обратно (инженерный харнес)
python3 tools/toggle_skills.py --enable
python3 tools/toggle_skills.py --status   # -> 🟢 Скилы АКТИВНЫ
```

Подробный сценарий A/B-эксперимента с разбором ошибок вайб-кодинга (OOM, разрыв контрактов DTO, разрушение слоёв) и профессиональной реализацией со скилом `fastapi-feature` описан в **[Главе 10 Ранбука Дня 1](Ранбук-День-1-Скилы-и-Харнес.md)**.

