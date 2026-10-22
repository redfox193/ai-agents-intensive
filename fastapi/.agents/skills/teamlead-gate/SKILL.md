---
name: teamlead-gate
description: "Оркестратор внешнего цикла приёмки (Techlead Gate): ведёт до 5 циклов Кодера, запускает CODE_GATE и Панель техлидов (Скептик, Реалист, Визионер), собирает итоговый вердикт READY, REWORK или ESCALATE в .ai-team/verdict.md. Триггеры: 'работай по скилу техлид', 'скил techlead-gate', 'приёмка техлида', 'teamlead gate'."
---

# Скил teamlead-gate: Оркестратор приёмки

Использовать, когда нужно довести задачу от спеки до независимой приёмки: запустить Кодера, проверить результат механическими гейтами, отдать пакет Панели техлидов и вынести итоговый вердикт. Внутренний протокол Панели описан в `.agents/skills/teamlead-panel/SKILL.md`. Кодер Цикла 1 работает по `.agents/skills/feature/SKILL.md`, Кодер Циклов 2..5 — по `.agents/skills/rework/SKILL.md`.

## Роль Оркестратора

Оркестратор — единственный writer состояния прохода и итогового вердикта.

1. **Код не пишет.** Ни продуктовый, ни тестовый. Исправляет только Кодер в новом цикле.
2. **Оценок за судей не придумывает.** Нет файла судьи или ответ мусорный — это технический исход, а не «примерная» оценка.
3. **Находки не понижает и не снимает.** Тяжесть меняют сами судьи в дебатах по правилам Панели.
4. **Файлы судей сохраняет сам:** судьи работают в режиме STRICT READ-ONLY, их ответ приходит в stdout, на диск его кладёт Оркестратор.
5. **Никакой веры на слово.** Слова «всё зелёное» не доказательство: нужны команда, код выхода или цитата `файл:строка`.

## Нерушимые правила приёмки

1. **Никакой веры на слово** — каждый пункт доказан командой или цитатой из файла.
2. **Право вето:** один нарушенный критерий из пяти не даёт ACCEPT.
3. **STRICT READ-ONLY для судей:** судья ничего не правит и не создаёт файлов.
4. **Zero Auth Leak (CWE-532):** токены, заголовок `Authorization` и `target_url` не попадают в логи и stdout сервиса.

## Вход приёмки

| Поле | Что это |
|---|---|
| `task_id` | идентификатор задачи, например `LINK-42` |
| `spec_refs` | пути к спеке, например `specs/LINK-42-enable-link.md` |
| `risk_plan_ref` | путь к риск-плану, например `docs/risk-plan-LINK-42.md` |
| `allowed_paths` | Blast Radius: для LINK-42 берётся из раздела 1 `specs/LINK-42-enable-link.md` ссылкой, список не копируется |
| модель | `opencode/deepseek-v4.1-flash-free` (семейство `deepseek-v4.1`), override через `OPENCODE_MODEL` |
| бюджет | до 5 циклов Кодера |

Режим приёмки уже готовой LINK-42: Кодер не запускается, сразу `CODE_GATE`, затем Панель.

## Внешний автомат (до 5 циклов)

```text
INIT → CODER (Цикл 1: feature; Циклы 2..5: rework) → CODE_GATE
     → ПАНЕЛЬ (INIT → R1 → D1 → D2 → D3 → FREEZE → C1) → ACCEPT | REJECT
REJECT → panel-rework-summarizer → handoff/panel-rework-brief.json → CODER (rework)
```

- **INIT:** прочитать спеку, риск-план, `docs/gate-rubric.md`; записать `task_id`, `cycle`, модель.
- **CODER:** Цикл 1 — `feature`, brief содержит `task_id`, цель, `spec_refs`, `risk_plan_ref`, `allowed_paths`, AC. Циклы 2..5 — `rework`, вход `handoff/panel-rework-brief.json` (задачи `RW-001`..) либо механический gate-failure brief с `CG-NNN` после красного CODE_GATE. Результат Кодера: `handoff/coder-NN.json` и `.ai-team/handoff-coder.md`.
- **CODE_GATE:** см. ниже. Красный CODE_GATE возвращает Кодера, расходует цикл и не является замечанием Панели.
- **ПАНЕЛЬ:** проход по протоколу `teamlead-panel`; основной бюджет 15 вызовов (3 R1 + 9 D + 3 C1), суммаризация — ещё один вызов сверх них.
- **ACCEPT / REJECT:** итог C1 по правилам Панели.
- **REJECT:** запустить `panel-rework-summarizer` (свежий процесс, read-only; вход — `findings-ledger`, файлы R1/D/C1 и diff), получить `handoff/panel-rework-brief.json`, проверить его `python3 scripts/validate_handoff.py handoff/panel-rework-brief.json`, передать Кодеру в режиме `rework`.
- **Технический выход `ESCALATE`:** `QUORUM_UNAVAILABLE` (нет файла или ответа судьи), `CONSENSUS_UNAVAILABLE` (мусор, неверный digest, противоречие кандидату), потолок 5 циклов (шестого запуска Кодера нет), устаревший пакет (хеши входов не совпали с файлами). Это не REJECT и новый запуск Кодера не открывает: решение за человеком.

## CODE_GATE: независимая проверка до Панели

Оркестратор запускает всё сам, слова Кодера не принимает. Команды (из корня репозитория):

```text
git diff --stat
uv run ruff check app tests
uv run basedpyright
uv run alembic upgrade head && uv run alembic check
uv run pytest tests/ -v
uv run python scripts/mutate_probe.py
```

- `git diff --stat` и полный список изменённых путей сверяются с `allowed_paths`; путь вне Blast Radius, правка `AGENTS.md` или защитных тестов — красный CODE_GATE.
- `alembic upgrade head` выполняется на временной БД (адрес задаётся переменной окружения `DATABASE_URL`), `alembic check` после него обязан дать 0.
- Результат пишется в `.ai-team/code-gate.json`: команды, коды выхода, привязка sha256 входов (спека, риск-план, handoff Кодера). Любой код не 0 — CODE_GATE красный.

## Как запускается каждая роль

Каждый Кодер, судья, раунд и суммаризация — отдельный свежий процесс, stdin закрыт, без `--continue` и `--session`:

```text
opencode run -m "${OPENCODE_MODEL:-opencode/deepseek-v4.1-flash-free}" --format json "<brief>" < /dev/null
```

Модель одна на всех: семейство `deepseek-v4.1`. Один сбой транспорта допускает один повтор того же раунда и места, исходная попытка сохраняется.

## Что считает скрипт, а не модель

```text
python3 scripts/generate_proof.py manifest
python3 scripts/generate_proof.py ledger
python3 scripts/generate_proof.py freeze
python3 scripts/generate_proof.py
uv run python scripts/orchestrate_pipeline.py
uv run python scripts/orchestrate_pipeline.py --run-gates
uv run python scripts/orchestrate_pipeline.py --live
```

- `manifest` — паспорт прохода `.ai-team/panel/manifest.json` и его sha256.
- `ledger` — пересборка `findings-ledger.tsv` из файлов раундов; нормативен именно TSV.
- `freeze` — кандидат `.ai-team/panel/freeze.json` после D3, печатает digest для C1.
- `generate_proof.py` без подкоманды — проверка всего пакета, запись `consensus-proof.json` и `verdict.md`; выход 0 для READY, 1 для REWORK, 2 для ESCALATE.
- `orchestrate_pipeline.py` — быстрая проверка пакета (меньше 2 с); `--run-gates` выполняет настоящий CODE_GATE; `--live` ведёт цикл через `opencode run`.

## 5 критериев рубрики (`docs/gate-rubric.md`)

| № | Критерий | Доказательство |
|---|---|---|
| 1 | Спека: каждый пункт выполнен или назван невыполненным | спека против `app/` и тестов |
| 2 | Diff / Blast Radius: только разрешённые пути | `git diff --stat` против `allowed_paths` |
| 3 | Гейты: ruff, basedpyright, pytest, alembic check, mutate_probe | коды выхода в `.ai-team/code-gate.json` |
| 4 | Риск-план покрыт тестами, «не смотрел» заполнено честно | риск-план против `tests/` и handoff Кодера |
| 5 | Запреты: секреты и `target_url` не логируются, слои соблюдены, `AGENTS.md` не менялся | поиск по коду, границы слоёв, diff |

## Итог: `.ai-team/verdict.md`

Файл пишет `python3 scripts/generate_proof.py`, Оркестратор сверяет и публикует. Строка 1 строго одна из:

- `Вердикт: READY` — ACCEPT, единогласно в C1 либо без блокирующих находок;
- `Вердикт: REWORK` — согласованный REJECT, есть `blocking` находки;
- `Вердикт: ESCALATE` — технический исход, `verdict: null`.

```text
Вердикт: READY
(пустая строка)
VERDICT: ACCEPT           либо  VERDICT: REJECT  либо  verdict: null
Run: pass_id=…   Cycle: N   Artifact-SHA256: <sha256 ledger>
Consensus-Proof: .ai-team/consensus-proof.json (sha256 …)
Обоснование по критериям 1..5 и список находок со статусом
```

После вердикта: короткое резюме в чат — вердикт, цикл, пути к `verdict.md` и `consensus-proof.json`, число и статус находок. При `ESCALATE` назвать причину (`QUORUM_UNAVAILABLE`, `CONSENSUS_UNAVAILABLE`, потолок циклов, устаревший пакет, красный CODE_GATE) и остановиться.
