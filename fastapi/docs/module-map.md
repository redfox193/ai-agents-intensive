# linksvc — карта модулей и радиус влияния правки валидации TTL

Дата: 2026-10-19. Источник: чтение `app/` единого приложения (слои `api → services → repositories → models`) и `tests/`, файлы не менялись.
Дерево цепочки создания ссылки: `app/main.py`, `app/api/routes.py`, `app/schemas/link.py`, `app/services/link.py`, `app/repositories/link.py`, `app/models/link.py`, `app/db/session.py`; `tests/conftest.py`, `tests/flat_api/`.

## 1. Карта модулей (один модуль — одна строка)

- `app/main.py` — роль: сборка FastAPI и редирект `GET /{code}`; входы: `settings.DATABASE_URL`; выходы: `307` на `target_url` либо `404` (`Link not found` / `Link disabled`), вызов `service.resolve_link`.
- `app/api/routes.py` — роль: плоские HTTP-маршруты `/links`; входы: `POST /links (LinkCreate{target_url, ttl_seconds?, custom_code?})`, `GET /links/{code}`, `POST /links/{code}/disable|enable`; выходы: JSON `{short_code, target_url, disabled}`, ошибки `404`/`409`/`422`.
- `app/schemas/link.py` — роль: Pydantic-контракты и **валидация TTL**: `ttl_seconds: int | None = Field(None, gt=0, le=31536000)`; ошибка даёт `422` до вызова сервиса.
- `app/services/link.py` — роль: бизнес-логика (`create_link`, `resolve_link`, `disable_link`, `enable_link`); считает `expires_at = now + ttl_seconds`; выходы: `Link` или исключения `LinkNotFoundError` / `LinkInactiveError` / `LinkExpiredError` / `ShortCodeConflictError`.
- `app/repositories/link.py` — роль: персистентность (`get_by_code`, `create`, `set_active`, `increment_clicks`, `list_all`); выходы: `Link | None`, атомарный `UPDATE ... SET clicks = clicks + 1`; без валидации.
- `app/models/link.py` — роль: ORM-схема; выходы: таблица `links(id, short_code[16, unique], target_url[2048], clicks, disabled, expires_at, created_at, updated_at)`; TTL хранится как `expires_at`.
- `app/db/session.py` — роль: инфраструктура БД; входы: `DATABASE_URL`; выходы: `engine`, `async_session_factory`, зависимость `get_db()`.
- `tests/conftest.py` — роль: фикстуры `test_engine`, `db_session` и асинхронный `client` на SQLite в памяти; `tests/flat_api/conftest.py` — синхронный `TestClient` для плоских маршрутов.
- `tests/flat_api/test_characterization.py` — роль: характеризационные тесты API; выходы: проверки `roundtrip create→read`, `404` на missing, `422` на `ttl=-5` и `ttl=0`.

Цепочка создания: `routes.create_link(LinkCreate) → service.create_link → repository.create → models.Link → db.get_db`.

## 2. Радиус влияния правки валидации TTL

Текущая валидация: `app/schemas/link.py` (`Field(None, gt=0, le=31536000)`), Pydantic отвечает `422` до сервиса. Сервис лишь переводит `ttl_seconds` в `expires_at`.

### Затронуты напрямую (менять/проверять обязательно)
- `app/schemas/link.py` — место правила; любое изменение границ, типа (`float/str/bool`), `None` меняет условие и текст `422`.
- `app/services/link.py` — расчёт `expires_at`; если правило переедет в сервис, `422` из Pydantic сменится на ошибку сервиса и маппинг в `app/api/`.
- `tests/flat_api/test_characterization.py` — тесты `test_negative_ttl_rejected`, `test_zero_ttl_rejected` фиксируют текущее поведение; при новой границе нужны новые кейсы.
- `tests/integration/test_ttl_expiration.py` — истечение ссылки по `ttl_seconds=1` (`410`).

### Соседние — могут пострадать
- `app/repositories/link.py` — сохраняет `expires_at` без проверок; невалидное значение даст ошибку SQLite/Postgres или молчаливое усечение.
- `app/models/link.py` — `DateTime(timezone=True), nullable=True` без `CHECK`; ужесточение валидации без constraint в БД оставляет расхождение между API и прямыми вставками.
- `tests/flat_api/test_links.py` и roundtrip-тест `test_create_and_read_roundtrip` — создание без `ttl` (`None`) должно остаться валидным.

### Вне радиуса (не затрагивается)
- `app/db/session.py` — движок и сессии, к TTL отношения не имеет, если не добавляется миграция схемы.
- `GET /links/{code}` и `POST .../disable` (`app/api/routes.py`), `repository.get_by_code/set_active` — TTL не проверяют.

### Рекомендация для правки
Менять в одном месте (`app/schemas/link.py`, не дублировать в сервисе), оставить `422` консистентным, обновить/добавить тесты на границы (`1`, `0`, `-5`, `None`, max, не-int).
