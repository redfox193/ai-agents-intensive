# AGENTS.md

Монолит `linksvc` (links + analytics + billing): приложение `app/` и `alembic/` едино для трёх дней
и доступно с Дня 1, в Дне 3 добавлены скилы и верификаторы.
Это финальное состояние Дня 3 (`day-3` = `snap-6`): ниже названы только файлы, скилы и команды, которые лежат на нём.

Перед любой работой прочитай по порядку:

1. `.agents/AGENTS.md` — правила репозитория: границы слоёв, миграции, запреты против обхода проверок.
2. `docs/module-map.md` — карта модулей цепочки создания ссылки и радиус влияния правки (вход скила `small-fix`).
3. `docs/INDEX.md` — карта доменов монолита (до 100 строк), дальше — нужный файл из `docs/domains/`.
4. `.planning/STATE.md` — на какой волне остановился конвейер (`.agents/skills/open-gsd-pipeline`).
5. `specs/blast-radius.json` — бюджет изменений: не больше 7 файлов, замороженное ядро не трогать.

Скилы лежат в `.agents/skills/<имя>/SKILL.md`, сейчас их 15: 7 из Дня 1, 2 из Дня 2 и 6 скилов Дня 3 (`monolith-knowledge-graph`, `open-gsd-pipeline`, `spec-kit-ears`, `architecture-layers-linter`, `blast-radius-guard`, `techlead-gate`).

Проверка перед отчётом (все команды ниже есть на этом срезе и должны вернуть `0`):

```bash
uv run ruff check .
uv run pytest -q
uv run python tools/plan_checker.py
uv run python tools/ears_linter.py
uv run python tools/verify_techlead_gate.py
```

`verify_techlead_gate.py` запускает пять проверок подряд: базу знаний, граф зависимостей,
линтер слоёв, Blast Radius и `pytest tests/unit tests/integration`.
