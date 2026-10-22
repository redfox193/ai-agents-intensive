# День 2. Оркестрация: Оркестратор, Кодер и Панель техлидов

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
От дня к дню растут скилы агента и обвязка: в Дне 2 добавлены скилы приёмки и доработки
и внешний цикл **Оркестратор, Кодер, Панель техлидов**.

В `.agents/skills/` лежат базовые скилы Дня 1 и скилы Дня 2. Скилов монолита Дня 3 здесь нет —
они появляются на ветке `day-3`.

## Роли Дня 2

Ролей ровно три, других нет:

| Роль | Скил | Что делает |
| --- | --- | --- |
| Оркестратор | `teamlead-gate` | Ведёт до 5 циклов, сам запускает CODE_GATE, отдаёт пакет Панели, публикует `.ai-team/verdict.md`. Код не пишет и за судей не оценивает |
| Кодер | `feature` (Цикл 1), `rework` (Циклы 2..5) | Пишет код по спеке, затем исправляет по `handoff/panel-rework-brief.json` |
| Панель техлидов | `teamlead-panel` | Три судьи (`judge-1..3`) со шляпами Скептик, Реалист, Визионер: R1, три раунда дебатов D1..D3, FREEZE и слепой финал C1; встроенная функция `panel-rework-summarizer` превращает согласованный REJECT в бриф для Кодера |

Каждый Кодер, судья, раунд и суммаризация — отдельный свежий процесс
`opencode run -m <модель> --format json "<бриф>"` со стдином `/dev/null`, без продолжения сессий.
Модель одна: `opencode/deepseek-v4.1-flash-free` из `opencode.json` (`model` и `small_model`);
`OPENCODE_MODEL` и `--model` принимают только её, любой другой ID оркестратор отклоняет.

## Скилы (`.agents/skills/`)

| День | Скил | Для чего |
| --- | --- | --- |
| 1 | `investigate-codebase`, `characterization-tests`, `tests-unit`, `tests-integration`, `database-migration`, `fastapi-feature`, `safe-refactoring` | Базовые скилы одиночного инженера (описаны в `README.md` ветки `day-1`) |
| **2** | `small-fix` | Точечная правка в 1-2 файлах: baseline, правка в разрешённых путях, гейты, отчёт |
| **2** | `teamlead-gate` | Оркестратор приёмки: до 5 циклов, CODE_GATE, вердикт READY, REWORK или ESCALATE. Запускается фразой «Работай по скилу техлид»; алиасы `teamlead`, `techlead`, `techlead-gate` |
| **2** | `teamlead-panel` | Панель техлидов: Скептик, Реалист, Визионер, дебаты D1..D3, FREEZE, слепой C1, функция `panel-rework-summarizer` |
| **2** | `feature` | Кодер, Цикл 1: реализация по спеке и риск-плану |
| **2** | `rework` | Кодер, Циклы 2..5: исправление по `handoff/panel-rework-brief.json` |

## Что лежит в каталоге

| Путь | Назначение |
| --- | --- |
| `AGENTS.md` | Правила `linksvc`: границы слоёв, проверки командой, запрет прямого коммита в `main` |
| `app/` | Единое приложение (то же, что в Дне 1 и Дне 3): `main.py`, слои `api/`, `services/`, `repositories/`, `models/`, `schemas/`, `core/`, `db/`, домен links + analytics + billing |
| `alembic.ini`, `alembic/` | Миграции Alembic: `env.py` читает `DATABASE_URL`, ревизии `versions/001…003` |
| `tests/` | `flat_api/` (контракт LINK-42: слепок поведения, редирект, disable/enable, счётчик кликов), `unit/`, `integration/`, `characterization/`; `agent-battle/` — тест атомарного счётчика |
| `specs/LINK-42-enable-link.md` | Спецификация задачи LINK-42: включение и отключение ссылки |
| `docs/` | `INDEX.md`, `module-map.md`, `decisions.md`, `glossary.md`, риск-планы, `gate-rubric.md` |
| `prompts/01-coder.md`, `prompts/03-gate.md` | Промпты ролей Кодера и Оркестратора приёмки |
| `.ai-team/handoff-coder.md` | Текстовая проекция handoff Кодера (эталон) |
| `.ai-team/code-gate.json` | Свидетельство CODE_GATE: команды, коды выхода, привязка sha256 входов |
| `.ai-team/panel/` | Проход Панели: `manifest.json`, файлы судей `r1/`, `d1/`, `d2/`, `d3/`, `c1/`, реестр `findings-ledger.tsv`, `freeze.json` |
| `.ai-team/verdict.md`, `.ai-team/consensus-proof.json` | Итог приёмки и доказательство консенсуса (пишет `generate_proof.py`) |
| `scripts/` | `orchestrate_pipeline.py`, `validate_handoff.py`, `generate_proof.py`, `mutate_probe.py` и тесты скриптов (`scripts/test_*.py`) |

## Запуск и проверки

Нужны Python 3.14 и [uv](https://docs.astral.sh/uv/). Тесты идут на SQLite в памяти, Postgres не нужен.

```bash
cd fastapi   # корень проекта на ветке day-2
uv sync
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest -q
DATABASE_URL=sqlite+aiosqlite:///./links.db uv run alembic upgrade head
DATABASE_URL=sqlite+aiosqlite:///./links.db uv run alembic check
uv run python scripts/mutate_probe.py        # мутации настоящих app/ против настоящих tests/
uv run pytest scripts -q                     # тесты скриптов приёмки
uv run python scripts/validate_handoff.py    # структура handoff Кодера, панели и брифа доработки
uv run python scripts/generate_proof.py      # проверка пакета Панели, verdict.md и consensus-proof.json
uv run python scripts/orchestrate_pipeline.py             # быстрая проверка пакета, меньше 2 с
uv run python scripts/orchestrate_pipeline.py --run-gates # настоящий CODE_GATE, затем проверка
uv run python scripts/orchestrate_pipeline.py --live      # внешний цикл через opencode run
uv run python scripts/orchestrate_pipeline.py --check-blast-radius # защищённые файлы и allowed_paths
```

Быстрая проверка печатает `GATE: PASS` и последней строкой `VERDICT: READY` (код 0). Красный шаг даёт
`VERDICT: FAIL (<шаг>)`, согласованный REJECT — `VERDICT: REJECT` (код 1), технический исход
(`QUORUM_UNAVAILABLE`, `CONSENSUS_UNAVAILABLE`, устаревший пакет) — `VERDICT: ESCALATE` (код 2).
`--live --dry-run` только печатает последовательность команд `opencode run`, ничего не запуская.

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

## Скрипты приёмки

- `scripts/mutate_probe.py` по очереди правит `app/repositories/link.py`, `app/services/link.py`,
  `app/schemas/link.py`, `app/main.py` (7 мутантов), запускает настоящий `pytest -q` и требует,
  чтобы тесты упали. Исходники восстанавливаются в `finally`. Нет `app/` или
  `tests/flat_api/test_links.py` — код 2, выживший мутант — код 1.
- `scripts/validate_handoff.py [путь ...]` проверяет handoff Кодера (`.ai-team/handoff-coder.md`,
  `handoff/coder-NN.json`), панель `.ai-team/panel/` и бриф `handoff/panel-rework-brief.json`.
  Без аргументов проверяет эталонный пакет; ошибки идут в stderr, код 1.
- `scripts/generate_proof.py` ничего не придумывает: подкоманды `manifest`, `ledger`, `freeze`
  собирают паспорт прохода, реестр находок `findings-ledger.tsv` и заморозку кандидата; без подкоманды
  скрипт проверяет весь пакет (заголовки судей, ротацию шляп, позиции в дебатах, привязки sha256,
  C1) и пишет `.ai-team/verdict.md` и `.ai-team/consensus-proof.json`. Кворум 3/3: нет файла судьи —
  `QUORUM_UNAVAILABLE`, нарушен формат или digest — `CONSENSUS_UNAVAILABLE`, оба — `ESCALATE`.
  В паспорт, `freeze.json` и `consensus-proof.json` входит `code_tree_sha256` (отпечаток `app/`,
  `tests/`, `alembic/`, `pyproject.toml`): правка кода после старта прохода даёт `STALE_PACKAGE`
  с причиной `STALE_CODE_TREE`, а `freeze` отказывается писать кандидата. `AMEND` автора на
  понижение тяжести действует только при единогласном `AGREE`.
  Судьи в репозитории — учебный эталон (`ORIGIN: reference-fixture`), не вывод живой панели;
  после правки спеки или кода пакет нужно собрать заново (`--live`).
- `scripts/orchestrate_pipeline.py` — внешний автомат. Без аргументов: наличие артефактов, handoff
  Кодера, свидетельство CODE_GATE и проверка Панели. `--run-gates`: настоящие `ruff`, `basedpyright`,
  `pytest`, `alembic upgrade head` и `alembic check` на временной SQLite, `mutate_probe.py` и тесты
  скриптов, затем запись `.ai-team/code-gate.json`. `--live`: до 5 циклов (`--max-cycles`): Кодер
  (`feature`, затем `rework`), CODE_GATE, Панель R1..C1 по три параллельных процесса `opencode run`,
  при согласованном REJECT — `panel-rework-summarizer`. Шаг CODE_GATE `--check-blast-radius`
  проверяет, что защищённые файлы (`AGENTS.md`, `pyproject.toml`, `uv.lock`, спека, скилы Дня 1)
  не тронуты, а правки `app/`, `tests/`, `alembic/` входят в список разрешённых файлов спеки; дифф
  для судей ограничен этими каталогами. Вокруг каждого судьи снимается отпечаток дерева: запись вне
  `.ai-team/` и `handoff/` — `JudgeReadOnlyViolationError` и `ESCALATE`. Журнал пишется в
  `handoff/pipeline-execution.log`.

## Что взято из других источников

- `tests/flat_api/test_link_toggle.py` проверяет `disable`/`enable`; счётчик кликов и редирект
  проверяет `tests/flat_api/test_links.py`, поэтому листинг из ранбука с колонкой `clicks` здесь заменён
  рабочими тестами.
- Каталог `handoff/` создаётся скриптами при запуске и в репозиторий не входит.
