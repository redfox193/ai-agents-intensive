---
name: tests-unit
description: >
  Пишет unit-тесты сервисного слоя: Fake-репозитории вместо моков, async, от
  acceptance criteria. Звать при новой фиче/багфиксе для изолированного тестирования
  бизнес-логики без БД.
owner: tbd
freedom: guided
last_reviewed: 2026-07-13
---

# Skill: Unit Tests

## Когда применять

Тестирование бизнес-логики сервисного слоя изолированно от БД/сети. Полный путь
HTTP→БД — `tests-integration.md`; фронтенд — `tests-frontend.md`; стратегия покрытия
для эпиков — `tests-strategy.md`.

## Входной контракт

| Вход | Формат / где взять | Нет → действие |
|---|---|---|
| Acceptance criteria / DoD задачи | PRD (FR-ID) или T-задача из architecture-doc | ASK — тест без критерия проверяет «текущее поведение», а не спеку |
| Контракт тестируемого слоя | сигнатуры сервиса/репозитория (architecture-doc или код) | вывести из кода интерфейса — НЕ из тела реализации |
| Для багфикса: воспроизведение | шаги/данные из Jira | ASK — см. bugfix.md |

**Правило слепоты:** тесты пишутся от acceptance criteria и контракта (сигнатур),
НЕ от чтения тела реализации — тест, написанный «по коду», подтверждает баги как
ожидаемое поведение. Для новой логики: сначала тест по AC (красный) → потом код.

## Алгоритм написания unit тестов

### 1. Подготовка
- Прочитать `.agents/agents/testing.md` — стратегия тестирования.
- Unit тесты тестируют **сервисный слой** изолированно от БД.
- **Проект полностью async**: `LinkService` — async, `LinkRepository` — async. Тесты тоже async.

### 2. Структура
- Файлы: `tests/unit/test_<module>.py`.
- Фабрика: `make_service()` создаёт сервис с **Fake**-репозиторием.
- Fake-репозиторий: хранит данные в обычном `dict` — без БД, **с теми же async-сигнатурами** что у реального `LinkRepository` (методы `async def`, иначе `await self.repository.X(...)` в сервисе сломается).

### 3. Правила
- Только `pytest`, функции. Никакого `unittest.TestCase`.
- **Все тестовые функции `async def`** — у нас в `pyproject.toml` стоит `asyncio_mode = "auto"`, pytest сам запускает их в event loop без `@pytest.mark.asyncio`.
- Моки — только Fake-классы. Никакого `MagicMock`, `patch`.
- Fake-репозиторий — **все методы `async def`**, даже если внутри просто `return self._store[code]`. Сигнатуры должны соответствовать реальному `LinkRepository` (`add`, `get_by_code`, `increment_clicks`, `list_active`, `get_by_id`, `archive` — все async).
- Каждый тест создаёт свой экземпляр сервиса через фабрику.
- Аннотации `-> None` у каждой тестовой функции.
- `pytest.raises(ErrorClass, match=...)` — обязательно с `match=` и фрагментом сообщения.
- `from __future__ import annotations` первой строкой файла.

### 4. Что тестировать
- Успешный путь (happy path).
- Граничные случаи (пустая строка, None, дубликаты). **На каждый AC — минимум один
  граничный тест на краю диапазона** (типовой отказ AI-тестов: очевидный invalid-input
  есть, границы нет).
- Ошибочные случаи (несуществующий ID, невалидный ввод).
- Ориентир объёма: **≤ 5–6 осмысленных тестов на один acceptance criterion** — дальше
  отдача падает; больше — обоснуй (сложный инвариант, риск P0).
- Трассировка: в docstring теста — какой AC/FR-ID он проверяет.
- **Payload внешнего вызова, а не его код возврата.** Если сервис ходит во внешнюю систему,
  нужен тест на то, ЧТО ушло в запрос: рабочее ли значение параметра, который управляет
  сутью фичи. Fake внешнего клиента запоминает отправленный payload, тест утверждает про
  него. Проверка «вернулось 200 / вернулось не пусто» этот класс дефектов не ловит: внешний
  сервис честно отвечает успехом на просьбу ничего не делать.
- **Дефолт параметра проверяется отдельным тестом.** Собрать сервис из конфига по умолчанию,
  без окружения и без values, и утвердить, что фича при этом работает. Ноль, пустая строка
  и `None` у поля, ради которого фича существует, — это выключатель, а не настройка, и
  поймать его можно только тестом «на голом дефолте».

### Пример Fake-репозитория (async)

```python
class FakeLinkRepository:
    def __init__(self) -> None:
        self._store: dict[str, Link] = {}
        self._by_id: dict[int, Link] = {}
        self._next_id: int = 1

    async def add(self, code: str, original_url: str) -> Link:
        link = Link(
            id=self._next_id,
            code=code,
            original_url=original_url,
            clicks=0,
            created_at=datetime.now(timezone.utc),
            archived_at=None,
        )
        self._store[code] = link
        self._by_id[self._next_id] = link
        self._next_id += 1
        return link

    async def get_by_code(self, code: str) -> Link | None:
        return self._store.get(code)

    async def increment_clicks(self, code: str) -> Link | None:
        link = self._store.get(code)
        if link is None or link.archived_at is not None:
            return None
        updated = replace(link, clicks=link.clicks + 1)
        self._store[code] = updated
        self._by_id[updated.id] = updated
        return updated
```

### Пример теста (async)

```python
async def test_create_valid_url_returns_link() -> None:
    service = make_service()
    link = await service.create("https://example.com")
    assert link.code
    assert link.original_url == "https://example.com"


async def test_create_invalid_url_raises() -> None:
    service = make_service()
    with pytest.raises(ValueError, match="Invalid URL"):
        await service.create("not-a-url")
```

### 5. Проверка

**Шаг проверки обязателен — задача не считается завершённой, пока все команды ниже не выполнены и их вывод не показан.**

- `uv run ruff format .` — автоформатирование.
- `uv run ruff check --fix .` — автофикс автофиксимых правил (`I001`, `F401` и др.).
- `uv run ruff check .` — должно быть зелёно.
- `uv run pytest tests/unit/ -q` — **запустить pytest через инструмент выполнения команд и показать вывод**. Не утверждать «тесты пройдут» без реального запуска.
- Если pytest упал (IndentationError, SyntaxError, ImportError, AssertionError, AttributeError) — **исправить файл и перезапустить pytest**. Повторять пока не будет `passed`.
- В финальном ответе привести строку итога pytest (`N passed in Xs` или `N failed`) — иначе задача не выполнена.
- Для новой логики: показать, что тест **падал до реализации** (red → green) — тест,
  который никогда не падал, может тестировать Fake, а не поведение.

## Эскалация

- **ASK:** acceptance criteria отсутствуют или неоднозначны; тест требует данных,
  которых нет в задаче; тест стабильно падает из-за поведения, похожего на баг
  в чужом коде.
- **NEVER (решает только человек):** `skip`/`xfail` на существующий тест; снижение
  порога покрытия; правка acceptance criteria «под тест» (AC меняет product.md);
  удаление чужого падающего теста.

## Анти-паттерны

- ❌ Тест подгоняется под текущее поведение кода → ✅ тест от AC/спеки (красный до фикса)
- ❌ Тестировать поведение Fake/мока (assert на внутренности Fake) → ✅ assert на результат сервиса
- ❌ Fake возвращает только поля, нужные тесту → ✅ полная структура, как в реальности
- ❌ Тавтология: `assert result == result`, assert без утверждения о поведении → ✅ каждый assert проверяет пункт AC
- ❌ test-only методы в production-классах → ✅ тестируется публичный контракт
- ❌ Assert на код возврата внешнего вызова → ✅ assert на payload, который туда ушёл
- ❌ Тесты только на явно переданной конфигурации → ✅ отдельный тест на голых дефолтах
- ❌ Гнать coverage числом тестов → ✅ ≤5-6 на AC, каждый ловит свой класс ошибок

> Почему в списке есть пункты про payload внешнего вызова и про голые дефолты
> (GigaExplorator, 08.2026): параметр ожидания рендера имел `default=0`, ни разу не
> выставлялся в values, и ни один тест не смотрел ни на отправленный payload, ни на
> поведение при дефолтном конфиге. Внешний сервис отвечал 200, тесты были зелёные,
> а браузерный тир четыре дня снимал страницы до отрисовки: 27,6% пригодных из 4,13 млн.
> Любой из этих двух тестов поймал бы дефект за десять дней до прода.
