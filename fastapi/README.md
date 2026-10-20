# День 2. Оркестрация: конвейер Coder → Reviewer → Gate

Каталог `fastapi/` на ветке `day-2` — проект `linksvc` второго дня
интенсива Pytex «От вайб-кодинга к профессиональной AI-разработке». Это сервис коротких
ссылок: тесты и линтеры зелёные, на нём отрабатывается ролевой конвейер из нескольких
AI-сессий, которые передают друг другу файлы, а не историю чата.

**Приложение едино для трёх дней и доступно с первого дня.**
Побайтово одинаковы во всех трёх днях шесть объектов приложения и окружения: `app/`, `alembic/`,
`alembic.ini`, `uv.lock`, `docker-compose.yml`, `.env.example`.
`pyproject.toml` един по зависимостям и настройкам инструментов и отличается только учебным порогом
покрытия `fail_under`: `50` в Дне 1 (лестница `50 → 60 → 80 → 85`) и `85` в Днях 2-3.
Каталог `tests/` (вместе с `agent-battle/`) даёт общую базу из 98 тестов приложения во всех трёх днях;
в Дне 3 к ней добавлены два файла тестов обвязки — `tests/unit/test_kb_sync.py` (со `snap-1`) и
`tests/unit/test_layer_linter_exhaustive.py` (со `snap-4`), всего 104 теста.
От дня к дню растут скилы агента (**7 → 9 → 15**) и обвязка: в Дне 2 добавлены 2 скила и конвейер
Coder → Reviewer → Gate.

В `.agents/skills/` лежат **9 скилов**: 7 базовых скилов Дня 1 и 2 скила Дня 2.
Скилов монолита Дня 3 здесь нет — они появляются на ветке `day-3`.

## Скилы (`.agents/skills/`)

| День | Скил | Для чего |
| --- | --- | --- |
| 1 | `investigate-codebase`, `characterization-tests`, `tests-unit`, `tests-integration`, `database-migration`, `fastapi-feature`, `safe-refactoring` | Базовые скилы одиночного инженера (описаны в `README.md` ветки `day-1`) |
| **2** | `small-fix` | Точечная правка в 1-2 файлах: baseline, правка в разрешённых путях, гейты, отчёт |
| **2** | `pipeline` | Конвейер по спеке: Coder, затем CODE_GATE, Reviewer, три сессии Gate с голосованием 2 из 3 |

## Что лежит в каталоге

| Путь | Назначение |
| --- | --- |
| `AGENTS.md` | Правила `linksvc`: границы слоёв, проверки командой, запрет прямого коммита в `main` |
| `app/` | Единое приложение (то же, что в Дне 1 и Дне 3): `main.py`, слои `api/`, `services/`, `repositories/`, `models/`, `schemas/`, `core/`, `db/`, домен links + analytics + billing |
| `alembic.ini`, `alembic/` | Миграции Alembic: `env.py` читает `DATABASE_URL`, ревизии `versions/001…003` |
| `tests/` | `flat_api/` (контракт LINK-42: слепок поведения, редирект, disable/enable, счётчик кликов), `unit/`, `integration/`, `characterization/`; `agent-battle/` — тест атомарного счётчика |
| `specs/LINK-42-enable-link.md` | Спецификация задачи LINK-42: включение и отключение ссылки |
| `docs/` | `INDEX.md`, `module-map.md`, `decisions.md`, `glossary.md`, риск-планы, `gate-rubric.md` |
| `prompts/01-coder.md`, `02-reviewer.md`, `03-gate.md` | Промпты ролей конвейера |
| `.ai-team/` | Handoff-файлы между ролями (`handoff-coder.md`, `handoff-reviewer.md`, `handoff-gate.md`), `verdict.md` и голоса Gate-панели `panel-votes/*.json` |
| `scripts/` | `orchestrate_pipeline.py`, `validate_handoff.py`, `generate_proof.py`, `mutate_probe.py` |

## Запуск и проверки

Нужны Python 3.14 и [uv](https://docs.astral.sh/uv/). Тесты идут на SQLite в памяти, Postgres не нужен.

```bash
cd ~/work/Python-AI/fastapi   # на ветке day-2
uv sync
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest -q
DATABASE_URL=sqlite+aiosqlite:///./links.db uv run alembic upgrade head
DATABASE_URL=sqlite+aiosqlite:///./links.db uv run alembic check
uv run python scripts/mutate_probe.py        # мутации настоящих app/ против настоящих tests/
uv run python scripts/generate_proof.py      # протокол панели из .ai-team/panel-votes/*.json
uv run python scripts/orchestrate_pipeline.py  # все проверки подряд, VERDICT: READY только при всех кодах 0
```

## API сервиса

Контракт LINK-42 (плоские маршруты; те же маршруты работают с Дня 1):

| Метод | Путь | Результат |
| --- | --- | --- |
| `POST` | `/links` | `201`: `short_code`, `target_url`, `disabled` (тело: `target_url` или `url`) |
| `GET` | `/links/{code}` | `200` с данными и `clicks`; `404` для отключённой и неизвестной |
| `POST` | `/links/{code}/disable`, `/links/{code}/enable` | `200`: `short_code`, `target_url`, `disabled`; `404` на неизвестный код |
| `GET` | `/{code}` | `307` на `target_url` и `clicks + 1`; `404 Link disabled` / `404 Link not found` |

Версионированные маршруты `/api/v1/links…`, `/api/v1/analytics/{code}`, `/billing/…` и `/health`
описаны в `README.md` ветки `day-1` и в `docs/` ветки `day-3`.

## Скрипты конвейера

- `scripts/mutate_probe.py` по очереди правит `app/repositories/link.py`, `app/services/link.py`,
  `app/schemas/link.py`, `app/main.py` (7 мутантов), запускает настоящий `pytest -q` и требует,
  чтобы тесты упали. Исходники восстанавливаются в `finally`. Нет `app/` или
  `tests/flat_api/test_links.py` — код 2, выживший мутант — код 1.
- `scripts/generate_proof.py` ничего не придумывает: читает голоса из `--votes-dir`
  (по умолчанию `.ai-team/panel-votes/`), сверяет sha256 спеки и риск-плана, запускает
  `ruff check` и `pytest`. Меньше трёх валидных голосов, меньше двух READY или красная
  проверка — `GATE: BLOCKED`, код 1. Голоса в репозитории — учебный эталон
  (`origin: reference-fixture`), не вывод живой панели; после правки спеки их нужно собрать заново.
- `scripts/orchestrate_pipeline.py` запускает настоящие `ruff`, `basedpyright`, `pytest`,
  `alembic upgrade head` и `alembic check` на временной SQLite, `mutate_probe.py`, проверку
  артефактов `.ai-team/` и `generate_proof.py`. Первая ошибка — `VERDICT: FAIL (<шаг>)` и код 1.
  Журнал пишется в `handoff/pipeline-execution.log`.

## Что взято из других источников

- `tests/flat_api/test_link_toggle.py` проверяет `disable`/`enable`; счётчик кликов и редирект
  проверяет `tests/flat_api/test_links.py`, поэтому листинг из ранбука с колонкой `clicks` здесь заменён
  рабочими тестами.
- Каталог `handoff/` создаётся скриптами при запуске и в репозиторий не входит.
