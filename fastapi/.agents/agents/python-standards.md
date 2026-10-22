# Python Development Standards

Стандарт разработки проекта. Документ — единый источник проверяемых правил. Ссылки на параграфы вида «§5», «§13» используются в `.agents/agents/code.md`. Все правила обязательны для нового кода. Старый код приводится к стандарту по мере касания.

***

## Главные принципы

1. **Читаемость прежде всего.** Код больше читают, чем пишут. Лишние list-comprehension'ы ради сокращения строк — нет; явный `for` если он понятнее — да. Хитрый «быстрый» код — только когда профилирование показало что это узкое место.
2. **Без типов проект не пишется.** Все функции и методы — с аннотациями параметров и возвращаемого типа, включая `-> None`. `basedpyright` в strict-режиме обязателен.
3. **Словари — зло на границах.** `dict` запрещён как публичный контракт между модулями / слоями / сервисами. Внутри одной функции `dict` допустим как промежуточная структура. На границах — `dataclass` / Pydantic / domain-объекты.
4. **Секреты не попадают в код и коммиты.** Только через `.env` (локально) и переменные окружения (на серверах). Любой API-ключ в `pyproject.toml`, тестах или примерах — баг, не фича.
5. **Перед коммитом проходят локальные проверки.** Один шорткат: `uv run ruff check . && uv run basedpyright && uv run pytest -q`. Если упало — коммит не уходит.
6. **Async-проект остаётся async.** Любой sync DB-вызов в async-контексте блокирует event loop и обнуляет выгоду от async FastAPI. См. §5 ниже.

***

## Запреты — нарушение блокирует merge

| # | Конструкция | Почему запрещена |
|---|---|---|
| 1 | `except Exception: pass` | Глушит ошибки без диагноза. Источник «случайных» падений в проде. Ловим конкретный тип, либо логируем и пробрасываем. |
| 2 | `def foo(items=[])` | Mutable default — общий между вызовами. Тысячи багов в Python-учебниках на этом примере. Использовать `items: list[X] \| None = None` + `if items is None: items = []`. |
| 3 | `def get_stats() -> dict` | `dict` как публичный контракт — не типизируется. Использовать DTO / dataclass / Pydantic. |
| 4 | `from sqlalchemy.orm import Session` в новом коде | Проект async. Только `AsyncSession` из `sqlalchemy.ext.asyncio`. |
| 5 | Синхронный `requests` / `psycopg.connect` в async-handler'е | Блокирует event loop. Использовать `httpx.AsyncClient` / `AsyncSession`. |
| 6 | `Optional[X]` / `List[X]` / `Dict[K, V]` | Устаревший pre-PEP-604 стиль. Использовать `X \| None` / `list[X]` / `dict[K, V]`. |
| 7 | Magic numbers в логике (`if len(x) > 255`) | Не самодокументируются. Выносить в именованные константы в начало модуля. |
| 8 | Бизнес-логика в route handler (`api/links.py`) | Нарушает слоевую архитектуру. Логика → `services/`, handler делает только парсинг запроса и формирование ответа. |
| 9 | `# noqa` / `# type: ignore` без объяснения | Подавление линтера без причины — техдолг без следа. Если ставишь — добавляй комментарий **почему**. |
| 10 | `--no-verify` / `SKIP=hook git commit` | Обход pre-commit'а. Никогда. Если хук падает — разбираешься, не обходишь (см. AGENTS.md). |
| 11 | `print()` для логирования | Нет уровня, нет полей, не идёт в централизованный сбор. Использовать `structlog` (см. §13). |
| 12 | `logger.info(f"order {order_id} done")` | Каждый event уникален, агрегация по шаблону невозможна. `logger.info("order done", order_id=order_id)` (см. §13). |
| 13 | Секреты / токены / Authorization-заголовки в kwargs логгера | Логи уходят в централизованный сбор → утечка PII. См. §13 и `.agents/agents/security.md`. |
| 14 | `httpx.get(url, verify=False)` / `requests.get(url, verify=False)` | MITM-vulnerable. Для internal CA — `verify="/path/to/ca.pem"`. См. §14 и `.agents/agents/security.md`. |
| 15 | HTTP-клиент без `timeout=` | Запрос может висеть бесконечно, в async — таска не отпускает event loop. См. §5 и §14. |
| 16 | `subprocess.run(..., shell=True)` с user input | Command injection. Только list-форма + абсолютный путь + ограниченный env. См. §14. |

***

## §1. Типизация

### Аннотации обязательны везде

~~~python
# ❌ Нет аннотаций
def create_link(url, disabled=False):
    return {"id": 1, "url": url}


# ✅
def create_link(url: str, disabled: bool = False) -> Link:
    return Link(id=1, target_url=url, disabled=disabled)
~~~

### `from __future__ import annotations` — первая строка файла

Позволяет писать `X | None`, `list[X]` без проблем на любой версии Python, аннотации становятся ленивыми (не выполняются при импорте), что устраняет циклические импорты в типах.

### Современный стиль — PEP 604 (`X | Y`) и PEP 585 (`list[X]`, `dict[K, V]`)

~~~python
# ❌ Устаревший стиль
from typing import Optional, List, Dict, Union


def find(id: int) -> Optional[Link]: ...
def items() -> List[Dict[str, int]]: ...


# ✅ Современный стиль
def find(id: int) -> Link | None: ...
def items() -> list[dict[str, int]]: ...
~~~

### Возвращаемое `None` — всегда аннотируется

~~~python
# ❌
def clear_cache(self):
    self._cache = {}


# ✅
def clear_cache(self) -> None:
    self._cache = {}
~~~

### Protocol — для абстракций между слоями

Сервис зависит от `LinkRepositoryProtocol`, не от конкретного `LinkRepository`. Это даёт замену на Fake в тестах без подмены реальной БД.

***

## §2. Value Objects и DTO

`dict` запрещён как **публичный** возврат функции — на границе модулей контракт обязан быть типизирован.

### Value Object — неизменяемая доменная сущность

~~~python
@dataclass(frozen=True)
class Link:
    id: int
    code: str
    target_url: str
    clicks: int
    expires_at: datetime | None
~~~

### DTO — данные между слоями

~~~python
@dataclass(frozen=True)
class LinkStatsDTO:
    total_links: int
    total_clicks: int
    avg_clicks_per_link: float
~~~

### Где `dict` допустим

Только как **приватная промежуточная структура внутри одной функции**, никогда — как возвращаемый тип публичного API.

***

## §3. Обработка исключений

### Не глотаем без логирования

~~~python
# ❌
try:
    result = risky()
except Exception:
    pass
~~~

### Ловим конкретный тип

~~~python
# ❌ Слишком широкий except
try:
    parsed = urlparse(value)
except Exception:
    return False

# ✅ Конкретный тип
try:
    parsed = urlparse(value)
except ValueError:
    return False
~~~

`except Exception` приемлем **только в самой внешней точке** (FastAPI middleware, top-level async-loop), и то с логированием.

### Fail fast

Если приложение запустилось с битой конфигурацией (отсутствует `DATABASE_URL`, кривой `AGENTPLATFORM_API_KEY`) — лучше упасть на старте, чем работать «как-нибудь» и упасть в 3 ночи.

### Не маскируем ошибки возвратом `None`

Если функция «может не сработать» по бизнес-логике (ссылка не найдена) — `None` оправдан. Если по техническим причинам (БД недоступна) — пробрасываем исключение, не возвращаем `None`. Иначе caller думает «данных нет», а реально «упало в коннекте».

***

## §4. SOLID

### S — Single Responsibility

Один класс / функция — одна причина для изменения.

~~~python
# ❌ Считает, форматирует и сохраняет
def process_links(links: list[Link]) -> str:
    rate = len([link for link in links if not link.disabled]) / len(links) * 100
    report = f"Active rate: {rate:.1f}%"
    save_to_file(report)
    return report


# ✅ Разделение
def calculate_active_rate(links: list[Link]) -> float: ...
def format_rate(rate: float) -> str: ...
def save_report(text: str, path: Path) -> None: ...
~~~

### D — Dependency Inversion

Сервис зависит от `Protocol`, а не от конкретной реализации.

~~~python
class LinkRepositoryProtocol(Protocol):
    async def get_by_code(self, code: str) -> Link | None: ...
    async def update(self, link: Link) -> Link: ...


class LinkService:
    def __init__(self, repo: LinkRepositoryProtocol) -> None:
        self.repo = repo
~~~

***

## §5. Async-правила — этот проект полностью async

Проект построен на FastAPI + `AsyncSession` + psycopg async. Любая sync-вставка в этот стек убивает производительность независимо от профилирования.

### Проверки, идущие в code review

- [ ] Все методы репозитория — `async def`, все обращения к БД через `await session.execute(...)` / `await session.commit()`.
- [ ] Сервис вызывает репозиторий через `await`, сам тоже `async def`.
- [ ] Route handler — `async def`, вызовы сервиса через `await`.
- [ ] Нет `from sqlalchemy.orm import Session` — только `from sqlalchemy.ext.asyncio import AsyncSession`.
- [ ] Нет sync HTTP-клиентов (`requests.get`) в async-handler'е — `httpx.AsyncClient` или `aiohttp`.
- [ ] Нет `time.sleep()` в async-функции — `await asyncio.sleep(...)`.
- [ ] Async-генераторы итерируются через `async for` / `anext()`, не через `next()`.

### Признаки sync-протечки

Если `psycopg`/SQLAlchemy в логах ругаются «attempted to call non-async method on AsyncSession», или ASGI-стек даёт RuntimeWarning про «coroutine was never awaited» — где-то sync-вставка. Найди и почини, не подавляй.

### Параллельные задачи — `asyncio.TaskGroup`, не `gather`

Для нескольких параллельных задач предпочитай `asyncio.TaskGroup` (Python 3.11+) перед `asyncio.gather`:

~~~python
# ✅ TaskGroup — отменяет остальные задачи при ошибке, ловится через ExceptionGroup
async def process_batch(ids: list[int]) -> list[User]:
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(fetch_user(uid)) for uid in ids]
    return [t.result() for t in tasks]
~~~

`gather(*coros, return_exceptions=True)` оставляем для случаев, когда ошибки **обрабатываются отдельно** для каждой задачи (например, частичная выгрузка где fail одной не должен прерывать остальные).

### Тайм-ауты на внешние вызовы — обязательны

~~~python
# ✅
try:
    result = await asyncio.wait_for(fetch_data(), timeout=5.0)
except TimeoutError:
    logger.error("fetch_data timed out")
    raise
~~~

Любой внешний вызов (HTTP, БД, очередь) без явного таймаута — анти-паттерн. В `httpx.AsyncClient` используем `httpx.Timeout(connect, read, write, pool)` (см. `.agents/agents/security.md` §6).

***

## §6. KISS — Keep It Simple

Признаки нарушения:
- функция длиннее ~40 строк;
- вложенность более 3 уровней `if`/`for`/`try`;
- параметры-флаги (`mode="fast"`, `use_cache=True`) — обычно две функции под одним именем, лучше разделить.

~~~python
# ❌
def is_valid_title(title: str) -> bool:
    return bool(
        title is not None
        and isinstance(title, str)
        and len(title.strip()) > 0
        and not title.strip() == ""
    )


# ✅
def is_valid_title(title: str) -> bool:
    return bool(title.strip())
~~~

***

## §7. DRY — Don't Repeat Yourself

Одна и та же логика — в одном месте. Если копируется из файла в файл (`fetch_with_retry`, форматирование даты, парсинг URL) — выносится в утилиту или общую функцию модуля.

Но: преждевременная абстракция (одна функция используется 1 раз, на всякий случай вынесена) — хуже чем дубль из двух мест. Правило «трёх» — на третий дубль выноси.

***

## §8. Именование и константы

| Что | Стиль | Пример |
|-----|-------|--------|
| Функции / методы | `snake_case` | `create_link`, `get_by_code` |
| Классы | `PascalCase` | `LinkService`, `LinkRepositoryProtocol` |
| Константы модуля | `UPPER_SNAKE_CASE` | `MAX_URL_LENGTH = 2048` |
| Булевые | `is_*`, `has_*` | `is_archived`, `has_clicks` |
| Приватные | `_*` (одно подчёркивание) | `_generate_code` |

~~~python
# ❌ Magic numbers
if len(title) > 255:
    ...
if rate > 75:
    ...

# ✅
MAX_TITLE_LENGTH: int = 255
COMPLETION_RATE_EXCELLENT: float = 75.0
~~~

***

## §9. Аргументы функций

### Mutable default — запрещён

~~~python
# ❌
def process(items: list[str] = []) -> list[str]: ...


# ✅
def process(items: list[str] | None = None) -> list[str]:
    if items is None:
        items = []
    ...
~~~

### Параметров много — пакуем в DTO

Более 4-5 параметров — признак что функция знает о слишком многих вещах. Объединяй в `dataclass` / Pydantic-модель.

### Желательно: одна точка возврата

Не правило, но облегчает чтение. Особенно если возвращаемое значение — DTO с десятком полей.

***

## §10. Слоевая архитектура

Проект следует разделению `api/` → `services/` → `repositories/` → `db/models.py`. Доменные сущности живут в `domain/`. Каждый слой импортирует **только нижестоящий**.

| Слой | Импортирует | Не импортирует |
|------|------------|----------------|
| `domain/` | ничего из проекта | всё проектное |
| `db/models.py` | `domain/` (опционально) | `services/`, `api/` |
| `repositories/link_repository.py` | `domain/`, `db/models.py` | `services/`, `api/` |
| `services/` | `domain/`, Protocol репозитория | `db/models.py` напрямую |
| `api/` | `services/`, `domain/` | `db/`, `repositories/` напрямую |
| `validators/` | `domain/` (если нужно) | `db/`, `services/`, `api/` |

Конкретные правила:
- API не лезет в `LinkRepository` мимо сервиса, даже «просто чтобы быстрее» — теряется единая точка валидации.
- Сервис не лезет в `LinkModel` (SQLAlchemy-модель) напрямую — только через репозиторий.
- Бизнес-логика **не живёт** в роуте — handler делает парсинг запроса, вызов сервиса, формирование ответа.

***

## §11. Работа с БД и миграциями

- Любой запрос к БД — через **репозиторий**, не из сервиса напрямую и не из роута.
- Сложные `JOIN`/агрегации — в репозитории как отдельный метод с типизированным DTO в return, не «возвращаем `Row` и разбираем сверху».
- Изменение схемы — только через Alembic-миграцию. Никаких `Base.metadata.create_all(engine)` вне `tests/`.
- `alembic upgrade head` запускается **до** старта приложения (в проекте — отдельной командой `uv run alembic upgrade head` в runbook'е или деплой-скрипте, не из `app.startup`).
- Длинные миграции (создание индекса, бэкфилл) — отдельная миграция без `op.execute(...)` на блокирующих DDL без `CONCURRENTLY`.

***

## §12. Документация — см. `.agents/agents/docs.md`

Любая публичная функция / метод / класс **должна иметь docstring** — это часть стандарта кода, не отдельная задача. Без docstring код **не идёт в merge**.

Краткие правила (детали и форматы — в `.agents/agents/docs.md`):

- **Docstring** на каждой публичной функции/методе/классе. Формат — Google-style: одна строка-резюме, потом `Args:` / `Returns:` / `Raises:` если нужны. **Язык — русский** (имена параметров остаются английскими, описание — русское).
- **CHANGELOG.md** обновляется на любое пользовательское изменение, под `[Unreleased]` → `Added` / `Changed` / `Fixed` / `Deprecated` / `Removed` / `Security`. Внутренний рефакторинг без изменения поведения **в CHANGELOG не попадает**.
- **ADR** в `docs/adr/NNNN-short-name.md` — когда решение затрагивает несколько модулей или меняет публичный контракт. Обязательные секции: Status, Context, Decision, Consequences.
- **README.md** — обновляется когда меняются эндпоинты, ENV-переменные, команды запуска, зависимости. Устаревший README — блокер мержа.

Запрещено:

- Коммит публичного API без docstring.
- Docstring повторяющий имя функции (`def get_user(): """Get user."""`) — лучше без docstring, чем с мусорным.
- Новый эндпоинт / breaking change без записи в CHANGELOG.

***

## §13. Логирование — см. `.agents/agents/logging.md`

Структурное логирование — обязательная часть стандарта. Подробности (конфигурация structlog, redact_secrets, middleware с `request_id`) — в `.agents/agents/logging.md` (файл создаётся в Шаге 8.1.2). Сами модули `app/logging.py` и `app/middleware/request_id.py` воркшоп не создаёт: это референсные фрагменты, которые ты добавляешь сам, если доводишь логирование до prod-вида. Здесь — проверяемые правила, которые ловятся в code review.

### Что использовать

- **Сервис / приложение** — `structlog` (JSON в prod, ConsoleRenderer в dev).
- **Библиотека / пакет** — стандартный `logging` (не навязывай формат потребителю).
- `print()` для логирования **запрещён** — нет уровней, нет полей, не идёт в централизованный сбор.

### Уровни

| Уровень | Когда |
|---|---|
| `debug` | Детали для локальной отладки; в prod отключено |
| `info` | Значимые события: запуск, завершение задачи, бизнес-событие |
| `warning` | Нештатная ситуация, с которой код справился (retry, fallback) |
| `error` | Ошибка, операция не выполнена — требует внимания |
| `critical` | Сервис неработоспособен — требует немедленной реакции |

### Правила (нарушение блокирует merge)

- **kwargs, не f-строки** в сообщении. Сообщение-event стабильное, параметры отдельно — иначе агрегация по шаблону невозможна:

~~~python
# ❌
logger.info(f"Processing order {order_id}")

# ✅
logger.info("processing order", order_id=order_id)
~~~

- **Не логировать секреты.** Пароли, токены, PII, Authorization-заголовки, cookie — никогда. В структурном пайплайне работает рекурсивный processor `redact_secrets` (детали в `.agents/agents/logging.md`), но это последняя линия — на уровне `logger.info(...)` явных секретов быть не должно.
- **Не логировать в горячих циклах.** Лог в hot path под нагрузкой превращается в I/O bottleneck. Логируй итог цикла или сэмплируй.
- **`request_id` / `trace_id` через `structlog.contextvars`.** FastAPI middleware биндит `request_id` в начале запроса (`bind_contextvars`), очищает в конце (`clear_contextvars`). Все логи в рамках запроса автоматически получают это поле.
- **Формат в prod — JSON.** Одна строка = один JSON-объект. Это нужно ELK / Loki / Datadog для парсинга.

***

## §14. Безопасность — см. `.agents/agents/security.md`

Прикладная безопасность Python — расширенный набор паттернов в `.agents/agents/security.md` (раздел «Security-паттерны Python»). Здесь — три принципа и компактный чеклист на code review.

### Принципы

1. **Не доверяй входным данным.** Всё что приходит извне (HTTP-тело, query, header, Kafka, файл, CLI-аргумент) — валидируется через Pydantic на границе системы, а не глубоко внутри.
2. **Минимум привилегий.** Сервис, процесс, токен, IAM-роль — каждый работает с минимальным набором прав.
3. **Defense in depth.** Не полагайся на одну линию защиты. SQL-инъекция — параметризация **и** ORM **и** input validation **и** least-privilege DB-юзер.

### Чеклист безопасности (на каждом ревью)

- [ ] Секреты — только через ENV / vault, не в коде, не в логах, не в gitleaks-diff.
- [ ] SQL-запросы параметризованы (или через ORM); никаких f-строк в `execute(...)`.
- [ ] Входные данные валидируются на границе через Pydantic.
- [ ] Пароли — `bcrypt` / `argon2`, не `md5` / `sha1` / plain.
- [ ] Сравнение токенов / секретов — `hmac.compare_digest`, не `==`.
- [ ] Random для security — `secrets.token_urlsafe`, не `random`.
- [ ] HTTP-клиент — с явным `timeout=`, `verify=True`, без `follow_redirects` если URL контролирует пользователь.
- [ ] `subprocess` — `shell=False`, абсолютный путь, ограниченный env, `timeout=`.
- [ ] `pickle` / `yaml.load` / `xml.etree` без `defusedxml` — на untrusted input **не использовать**.
- [ ] File upload — MIME по содержимому (`python-magic`), UUID-имя, передекодирование (для картинок — через Pillow).
- [ ] JWT decode — explicit `algorithms=[...]`, verify `aud` / `iss` / `exp`.

Детали и примеры — в `.agents/agents/security.md`.

***

## §15. Современные фичи Python 3.14

Проект на Python >=3.14. Это означает, что доступны все возможности 3.10+, 3.11+, 3.12+, 3.13+, 3.14+. Использовать их **прямо** — это код-стиль, а не «факультативно».

### `match/case` вместо длинных `if/elif` по структуре (3.10+)

~~~python
# ✅
def handle_event(event: dict[str, object]) -> str:
    match event:
        case {"type": "link_created", "id": int(link_id)}:
            return f"new link: {link_id}"
        case {"type": "link_deleted"}:
            return "link removed"
        case {"type": str(unknown)}:
            return f"unknown event: {unknown}"
        case _:
            return "malformed event"
~~~

`if isinstance(...) and "x" in dct and ...` — переписывай на `match`, когда веток ≥ 3 и они ветвятся по структуре.

### `Self` для fluent-интерфейсов (3.11+)

~~~python
from typing import Self


class QueryBuilder:
    def where(self, predicate: str) -> Self:
        self._predicates.append(predicate)
        return self

    def limit(self, n: int) -> Self:
        self._limit = n
        return self
~~~

Раньше требовался `TypeVar('Q', bound='QueryBuilder')` плюс forward references — теперь одна аннотация.

### `ExceptionGroup` (3.11+) + `TaskGroup`

См. §5 — для конкурентного кода, где несколько задач могут упасть одновременно, ошибки приходят пачкой через `ExceptionGroup`:

~~~python
try:
    async with asyncio.TaskGroup() as tg:
        tg.create_task(fetch_users())
        tg.create_task(write_audit_log())
except* DatabaseError as eg:
    for err in eg.exceptions:
        logger.error("db error in batch", err=str(err))
~~~

`except*` — отдельный синтаксис для разбора `ExceptionGroup` по типу.

### PEP 695 — новый синтаксис type aliases (3.12+)

~~~python
# ❌ Старый стиль (TypeAlias из typing)
from typing import TypeAlias

UserId: TypeAlias = int
Maybe = list[int] | None

# ✅ PEP 695
type UserId = int
type Maybe[T] = T | None
type Point = tuple[float, float]
~~~

На 3.14 — используем новый синтаксис. Старый `TypeAlias`-импорт оставляем только при поддержке версий ниже 3.12 (у нас 3.14, не наш случай).

### `enum.StrEnum` (3.11+) для строковых констант

~~~python
# ✅
from enum import StrEnum


class LinkStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    DISABLED = "disabled"


# Сравнение с обычной строкой работает напрямую
if status == "active":
    ...
~~~

`StrEnum` поверх `Enum` экономит boilerplate и работает с JSON / БД / API без `.value`.

### `with` со скобками для нескольких ресурсов (3.10+)

~~~python
# ❌ Длинная вложенность
with open("input.txt") as src:
    with open("output.txt", "w") as dst:
        dst.write(src.read())

# ✅ 3.10+ — со скобками
with (
    open("input.txt", encoding="utf-8") as src,
    open("output.txt", "w", encoding="utf-8") as dst,
):
    dst.write(src.read())
~~~

### `@dataclass(slots=True, frozen=True)`

`slots=True` экономит память (нет `__dict__` на инстансе) и **ловит опечатки атрибутов** — `link.clcks = 5` падает с `AttributeError` вместо тихого создания нового поля. `frozen=True` запрещает мутацию — для Value Objects обязательно.

***

## Чеклист самопроверки перед commit

**Типы и структура**

- [ ] `from __future__ import annotations` в каждом новом файле
- [ ] Все параметры и возвращаемые типы аннотированы (включая `-> None`)
- [ ] Нет `Optional[X]` / `List[X]` / `Dict[K, V]` (PEP 604/585)
- [ ] Возвращаемые данные — DTO / Value Object / domain-объект, не `dict`
- [ ] Нет `except Exception: pass`, конкретные типы исключений
- [ ] Нет mutable defaults
- [ ] Magic numbers вынесены в константы

**Архитектура и async (§5, §10)**

- [ ] Async-слои не содержат sync-вызовов в БД / HTTP / sleep
- [ ] Параллельные задачи — через `asyncio.TaskGroup`, внешние вызовы — с `asyncio.wait_for(..., timeout=...)`
- [ ] Сервис не импортирует `db/models.py` напрямую
- [ ] Бизнес-логика не в route handler

**Логирование (§13)**

- [ ] Нет `print()` для логирования — только `structlog` / `logging`
- [ ] Сообщения без f-строк: `logger.info("event", key=value)`, не `logger.info(f"event {value}")`
- [ ] Нет секретов / токенов / PII в kwargs логгера
- [ ] Для request-жизненного цикла — `bind_contextvars(request_id=...)` в middleware

**Безопасность (§14)**

- [ ] Нет хардкода секретов / токенов / connection strings
- [ ] SQL — параметризованный (или через ORM), без f-строк
- [ ] Внешние данные валидируются через Pydantic на границе
- [ ] Пароли — `bcrypt` / `argon2`; сравнение токенов — `hmac.compare_digest`
- [ ] HTTP-клиенты — с `timeout=`, `verify=True`, без `follow_redirects` для user-controlled URL
- [ ] `subprocess` — `shell=False`, абсолютный путь, ограниченный env, `timeout=`

**Документация и changelog (§12)**

- [ ] Docstring на новых публичных функциях / методах (Google-style, на русском — см. §12 и `.agents/agents/docs.md`)
- [ ] CHANGELOG.md обновлён если меняется пользовательское поведение

**Автоматические проверки**

- [ ] `uv run ruff check .` — зелёный
- [ ] `uv run basedpyright` — зелёный
- [ ] `uv run pytest -q` — зелёный, coverage-гейт `--cov-fail-under=100` пройден
