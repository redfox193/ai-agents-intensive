# Handoff Кодер → Панель техлидов

Происхождение: эталонное состояние Дня 2 (учебный пример, `ORIGIN: reference-fixture`). Приложение `linksvc` общее для трёх дней: реализация LINK-42 присутствует в нём уже с Дня 1, а конвейер доказывает её командами и мутационной проверкой.

## Задача и затронутые файлы

- Задача: LINK-42 по `specs/LINK-42-enable-link.md` — `POST /links/{code}/disable` и `POST /links/{code}/enable`, редирект `GET /{code}`, миграция Alembic.
- Файлы реализации в пределах Blast Radius спеки (§1): `app/models/link.py` (поля `disabled`, `clicks`, гибрид `is_active`), `app/repositories/link.py` (`set_active`, `increment_clicks`), `app/services/link.py` (`resolve_link`, `disable_link`, `enable_link`), `app/main.py` (`redirect_to_target`), `app/api/routes.py` (disable и enable), `alembic/versions/001_initial_links.py`, `tests/flat_api/test_link_toggle.py`, `tests/flat_api/test_links.py`.
- Контракт ответа `LinkCreated` (`app/schemas/link.py`) и соответствие исключений кодам ответа (`app/api/errors.py`) использованы как есть: этих файлов нет в списке разрешённых путей спеки, и в рамках LINK-42 они не менялись.
- Не затронуты: `tests/flat_api/test_characterization.py`, `app/db/session.py`, `AGENTS.md`.

## Команды и коды выхода

- `uv run ruff check app tests`: 0.
- `uv run ruff format --check app tests`: 0 (77 files already formatted).
- `uv run basedpyright`: 0 (0 errors, 0 warnings).
- `uv run pytest -q`: 0 (98 passed).
- `uv run alembic upgrade head`: 0, затем `uv run alembic check`: 0 (на временной БД SQLite, `No new upgrade operations detected`).
- `uv run python scripts/mutate_probe.py`: 0 (7 из 7 мутантов убито).

## Решения

- Редирект `GET /{code}`: 307 для активной ссылки, 404 `Link disabled` для отключённой и 404 `Link not found` для несуществующей (`app/main.py:35-41`, `app/api/errors.py:16-19`).
- Правило активности проверяется в сервисе до инкремента (`app/services/link.py:109-114`), счётчик растёт атомарным `UPDATE ... SET clicks = clicks + 1` (`app/repositories/link.py:42`) только у активной ссылки.
- `disable` и `enable` идемпотентны: `set_active` выставляет флаг и возвращает ссылку (`app/repositories/link.py:45-52`); несуществующий код даёт 404.
- Значения `target_url` и заголовок `Authorization` в журнал потока LINK-42 не пишутся (`app/services/link.py:101, 141, 149`).

## Риски

- Схема БД меняется только ревизией Alembic; схему на PostgreSQL создаёт Alembic, а тесты строят её на SQLite через `Base.metadata.create_all`.
- Тест риска R-5 (`tests/flat_api/test_link_toggle.py:42`) проверяет подстроку из `target_url` и не проверяет заголовок `Authorization`.

## Не смотрел

- Нагрузочное поведение счётчика кликов на PostgreSQL под конкуренцией.
- Аппаратные сбои дисковой подсистемы SQLite (инфраструктурный риск из риск-плана).
- Каталоги `docs/archive` и файлы `*.bak` (правило 4 `AGENTS.md`).
