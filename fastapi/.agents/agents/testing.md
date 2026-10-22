# Testing rules

- Использовать `pytest`.
- Не использовать `unittest.TestCase`, `setUp`, `tearDown`.
- Во всех тестовых файлах писать `from __future__ import annotations`.
- **Проект полностью async**: handler'ы FastAPI async, сервис async, репозиторий async. Все тесты тоже **`async def`**, фикстуры с DB — `async`.
- В `pyproject.toml` стоит `asyncio_mode = "auto"` — `async def test_X()` запускается без `@pytest.mark.asyncio`.

## Unit tests

- Unit tests должны быть быстрыми и изолированными.
- Не использовать shared state между тестами.
- Не тестировать API в unit tests.
- Не использовать `MagicMock`, `patch` и `unittest.mock`, если можно сделать Fake-объект.
- **Fake-репозиторий повторяет async-сигнатуру реального**: все методы `async def`, чтобы `await self.repository.X(...)` в сервисе работал.
- Тестовые функции — `async def`, вызовы сервиса через `await`.

~~~python
class FakeRepository:
    def __init__(self) -> None:
        self._store: dict[str, Link] = {}
        self._next_id: int = 1

    async def add(self, link: Link) -> Link:
        stored = replace(link, id=self._next_id)
        self._store[stored.code] = stored
        self._next_id += 1
        return stored

    async def get_by_code(self, code: str) -> Link | None:
        return self._store.get(code)
~~~

- Fake-объекты предпочтительнее mock-подхода.
- Для in-memory хранения можно использовать `dict`, простой счётчик ID, `replace()` для иммутабельных копий.
- Если метод должен вернуть отсутствие сущности — проверять `is None`.
- Для ошибок использовать `pytest.raises(..., match=...)`.
- Имена тестов — в стиле `test_...`.

## Что проверять в unit tests

- Happy path.
- Edge cases: пустая строка, `None`, `0`, пробелы.
- Error cases: невалидный ввод, отсутствие сущности.
- Regression test на найденный баг.

## Integration tests

- Integration tests проверяют API целиком.
- HTTP-клиент: `httpx.AsyncClient` поверх `ASGITransport` (вызывается через `async with`).
- Состояние тестовой среды должно очищаться **до и после** каждого теста — autouse-фикстура с `async def`, чистка через `await session.execute(text("DELETE FROM ..."))`.
- Для этого удобно использовать `pytest.fixture(autouse=True)` + `async def`.
- Проверять реальные HTTP-статусы и JSON-ответы.
- `follow_redirects=False` пишем на `httpx.AsyncClient` явно. У самого httpx это и так дефолт, но у `starlette.testclient.TestClient` дефолт обратный (`True`), и при переезде на него тест молча начнёт ходить по 307-редиректу вместо проверки `Location`.

## Покрытие и доказательства

- Каждая задача на тесты явно объявляет область покрытия: один модуль или всё приложение.
- Для одного модуля используй `--cov=<python-модуль> --cov-branch --cov-report=term-missing --cov-fail-under=100`.
- Финальная проверка проекта всегда запускается для всего `app`:
  `uv run pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=100`.
- Нельзя получать процент изменением `app/`, настроек coverage или исключений. Запрещены
  `skip`, `xfail`, `pragma: no cover` и проверки без содержательного `assert`.
- Результат фиксируется в `reviews/<задача>-coverage.md`: точная команда, дата, проверенный
  commit SHA, число `passed`, итоговый процент, колонка `Missing` (`none` при 100%), уровни
  добавленных тестов и подтверждение отсутствия запрещённых обходов.
- Задача не завершена, пока объявленная область не имеет 100% branch coverage, все проверки
  не зелёные и отчёт не сохранён в Git.
