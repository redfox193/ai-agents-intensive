# День 3. Монолит, масштаб и приёмка

Каталог `fastapi/` на ветке `day-3` и на тегах `snap-0` … `snap-6` — монолит `linksvc` третьего дня
интенсива Pytex «От вайб-кодинга к профессиональной AI-разработке».

**Приложение едино для трёх дней и доступно с первого дня** (монолит links + analytics + billing).
Побайтово одинаковы во всех трёх днях шесть объектов приложения и окружения: `app/`, `alembic/`,
`alembic.ini`, `uv.lock`, `docker-compose.yml`, `.env.example`.
`pyproject.toml` един по зависимостям и настройкам инструментов и отличается только учебным порогом
покрытия `fail_under`: `50` в Дне 1 (лестница `50 → 60 → 80 → 85`) и `85` в Днях 2-3.
Каталог `tests/` (вместе с `agent-battle/`) даёт общую базу из 98 тестов приложения во всех трёх днях;
в Дне 3 к ней добавлены два файла тестов обвязки — `tests/unit/test_kb_sync.py` (со `snap-1`) и
`tests/unit/test_layer_linter_exhaustive.py` (со `snap-4`), всего 104 теста.
Меняются **скилы и обвязка**: **7 → 9 → 15** скилов. День 3 добавляет инструменты, которые ведут и принимают изменения монолита:
граф знаний, конвейер GSD, требования EARS, линтер слоёв, Blast Radius Guard и Techlead Gate.

В `.agents/skills/` лежат **15 скилов**: 7 из Дня 1, 2 из Дня 2 и 6 новых скилов Дня 3.

## Скилы (`.agents/skills/`)

| День | Скил | Для чего |
| --- | --- | --- |
| 1 | `investigate-codebase`, `characterization-tests`, `tests-unit`, `tests-integration`, `database-migration`, `fastapi-feature`, `safe-refactoring` | Базовые скилы одиночного инженера |
| 2 | `small-fix`, `pipeline` | Точечная правка и конвейер Coder → Reviewer → Gate |
| **3** | `monolith-knowledge-graph` | База знаний `docs/INDEX.md` и AST-граф зависимостей, Scoped Retrieval вместо чтения всего кода |
| **3** | `open-gsd-pipeline` | Задача волнами через `.planning/`: состояние, требования, дорожная карта |
| **3** | `spec-kit-ears` | Требования в синтаксисе EARS (`specs/billing-ears.md`) и их линтер |
| **3** | `architecture-layers-linter` | Границы слоёв schemas → core → services → api проверяются по AST |
| **3** | `blast-radius-guard` | Бюджет изменений (до 7 файлов) и замороженное ядро (`CODEOWNERS`) |
| **3** | `techlead-gate` | Приёмка: 5 проверок подряд одной командой |

## Что лежит в каталоге

| Путь | Назначение |
| --- | --- |
| `app/` | Единое приложение: `core/` (настройки, логирование, протоколы), `schemas/`, `services/`, `api/`, `db/`, `models/`, `repositories/`, `domain/` |
| `app/schemas/billing.py`, `app/core/protocols.py`, `app/services/billing.py`, `app/api/billing.py` | Домен Billing (те же файлы лежат в Днях 1-2) |
| `alembic/` | Миграции `001_initial_links`, `002_add_analytics_events`, `003_add_created_at_idx` |
| `docs/module-map.md` | Карта модулей цепочки создания ссылки (вход скила `small-fix`), из Дня 2 |
| `docs/INDEX.md`, `docs/domains/*.md` | Карта монолита и спецификации доменов |
| `.planning/` | `STATE.md`, `REQUIREMENTS.md`, `ROADMAP.md` конвейера GSD |
| `specs/` | `billing-ears.md` (EARS), `blast-radius.json` (бюджет изменений) |
| `tools/` | Верификаторы и вспомогательные утилиты (таблица ниже) |
| `tests/` | `unit/`, `integration/`, `characterization/`, `flat_api/` — тесты монолита, SQLite in-memory (плюс `agent-battle/` — тест атомарного счётчика). Общая база Дней 1-3 — 98 тестов; тесты обвязки Дня 3 `tests/unit/test_kb_sync.py` (со `snap-1`) и `tests/unit/test_layer_linter_exhaustive.py` (со `snap-4`) доводят набор до 104 |
| `.github/CODEOWNERS`, `.open-codeignore`, `.pre-commit-config.yaml` | Замороженное ядро, исключения для агента, локальные хуки |

## Запуск и проверки

Нужны Python 3.14 и [uv](https://docs.astral.sh/uv/). Postgres для тестов не нужен.
Команды выполняйте через `uv run`: верификаторы вызывают `python3` и `pytest` из окружения проекта.

```bash
cd ~/work/Python-AI/fastapi   # на ветке day-3 или на теге snap-N
uv sync
uv run ruff check .
uv run pytest -q
uv run python tools/plan_checker.py
uv run python tools/ears_linter.py
uv run python tools/verify_techlead_gate.py
```

| Утилита | Что проверяет или строит |
| --- | --- |
| `tools/verify_kb_sync.py` | Файлы из `docs/INDEX.md` существуют, индекс не длиннее 100 строк |
| `tools/build_dependency_graph.py --check-cycles` | В графе импортов нет циклов |
| `tools/verify_architecture_layers.py` | Нет запрещённых импортов между слоями |
| `tools/verify_blast_radius.py` | Изменено не больше 7 файлов, замороженное ядро не тронуто (по `git status`) |
| `tools/verify_techlead_gate.py` | Все четыре проверки выше и `pytest tests/unit tests/integration` |
| `tools/plan_checker.py`, `tools/gsd_fsm_runner.py` | Проверка и переходы состояния в `.planning/STATE.md` |
| `tools/ears_linter.py` | Требования в `specs/` соответствуют EARS |
| `tools/scoped_retrieval.py`, `build_call_graph.py`, `generate_repomap.py`, `compress_handoff.py` | Минимальный контекст для агента |
| `tools/benchmark_billing.py` | Замер задержки `POST /billing/charges/click` через TestClient |

## Контрольные срезы `snap-0` … `snap-6`

Теги лежат на истории ветки `day-3`. Перейти к срезу: `git checkout snap-3`.
Вернуться: `git checkout day-3`. На каждом срезе проходят `uv run pytest -q` и те верификаторы,
которые уже есть на этом срезе.

Приложение во всех срезах одно и то же; растёт набор скилов и обвязки.

| Тег | Что добавлено | Скилов |
| --- | --- | --- |
| `snap-0` | Единое приложение (links, analytics, billing) и скилы Дней 1-2 | 9 |
| `snap-1` | База знаний: `docs/INDEX.md`, `docs/domains/`, `verify_kb_sync` | 9 |
| `snap-2` | AST-граф, Scoped Retrieval, скил `monolith-knowledge-graph` | 10 |
| `snap-3` | Конвейер GSD (`.planning/`) и требования EARS: `open-gsd-pipeline`, `spec-kit-ears`, `ears_linter` | 12 |
| `snap-4` | Линтер слоёв: `verify_architecture_layers`, `architecture-layers-linter`, pre-commit | 13 |
| `snap-5` | Blast Radius Guard: `specs/blast-radius.json`, `CODEOWNERS`, `blast-radius-guard` | 14 |
| `snap-6` | Techlead Gate: `verify_techlead_gate`, скил `techlead-gate`, контрольные утилиты | 15 |

## Известные ограничения

- Приложение объединяет baseline Дня 1 (доменный слой `app/domain/`, плоские маршруты `/links`),
  контур Дня 2 (редирект `/{code}`, disable/enable) и монолит Дня 3 (`/api/v1/...`, analytics,
  billing). Сравнение `expires_at` учитывает наивное время SQLite, SSRF-валидатор лежит в
  `app/schemas/validators.py` (`app/core/security.py` реэкспортирует его), чтобы схемы не
  импортировали `app.core`.
- `app/api/links.py`, `app/schemas/links.py`, `app/services/links.py` — тонкие фасады над
  `link.py` и `app/api/v1/endpoints/links.py`: на них ссылается `docs/INDEX.md` (со `snap-1`);
  `app/repo.py`, `app/service.py`, `app/models_flat.py` — функциональные фасады имён Дня 2.
- `app/services/link_service.py` + `app/repositories/link_repository.py` — доменный сервис
  Дня 1 (протокол репозитория, атомарный счётчик, `agent-battle/`), независимый от HTTP-слоя.
- Репозиторий биллинга в `app/api/billing.py` хранит данные в памяти процесса.
