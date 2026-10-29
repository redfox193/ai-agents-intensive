---
name: rework
description: "Кодер, Циклы 2..5: исправляет только то, что назначено в handoff/panel-rework-brief.json (задачи RW-001..) или в механическом gate-failure brief с CG-NNN; по каждой задаче regression-тест red → green, минимальный фикс, неизменный baseline tests/, доказательство acceptance. Сдаёт handoff/coder-NN.json с rw_trace."
---

# Скил rework: Кодер, Циклы 2..5

Скил для повторных запусков Кодера во внешнем цикле `orchestrate-coder-reviewer-summarizer` / `teamlead-gate`. Первый цикл — скил `.agents/skills/feature/SKILL.md`. Здесь Кодер не проектирует заново, а закрывает конкретные замечания: после REJECT Панели техлидов или после красного CODE_GATE. Запуск: `opencode run -m "${OPENCODE_MODEL:-opencode-go/deepseek-v4.1-flash}" "<brief>" < /dev/null` (семейство `deepseek-v4.1`, свежий процесс, без памяти прошлых циклов).

Потолок: 5 циклов (по умолчанию в конвейере — 3). При исчерпании лимита Оркестратор выходит в `ESCALATE`.

## Вход

1. **Основной:** `handoff/panel-rework-brief.json`, его собрала функция `panel-rework-summarizer` из `findings-ledger` и файлов раундов. Контракт: `.agents/skills/teamlead-panel/references/panel-rework-brief-schema.md`.
2. **Механический:** gate-failure brief с типизированными `CG-NNN` (одна запись на упавшую команду CODE_GATE: команда, код выхода, фрагмент вывода). Применяется после красного CODE_GATE; находок Панели в нём нет.

Нет brief или не хватает обязательного поля — не угадывай, остановись и ответь `ASK: <имя поля>`.

## Что в brief и как это читать

| Раздел | Как относиться |
|---|---|
| `instructions` (`RW-001`, `RW-002`…) | **blocking**, выполнить все: файл, `line_hint`, `action`, `acceptance` |
| `non_blocking_followups` (`FU-001`…) | **не выполнять** без явного scope в brief Оркестратора |
| `excluded` | **не трогать**: дубли, снятые, чужой ключ, вне задачи |
| `terminal_objections` | учесть как контекст: возражения судей из финального раунда C1 |

## Порядок работы по каждой задаче `RW-NNN`

1. **Локализация.** Открой `file` и `line_hint`, найди причину, сверь с `evidence` и `rule_ref`. Если дефект не воспроизводится — не чини «на всякий случай», запиши это в `open_questions` и в `decisions`.
2. **Regression-тест red → green.** Сначала тест, который падает именно из-за этого дефекта; зафиксируй красный вывод; затем фикс; затем тот же тест зелёный.
3. **Минимальный фикс.** Ориентир: 1–15 изменённых строк продуктового кода на одну задачу. Больше — остановись, объясни причину в `decisions` и `risks`; лимит сам не ослабляй и не прячь объём в соседние файлы.
4. **Baseline неизменен.** Существующие тесты в `tests/` остаются зелёными и не правятся под фикс; защитные тесты и `AGENTS.md` не трогать.
5. **Acceptance.** Выполни команду `acceptance` из brief и запиши код выхода в `ac_results`.

## Anti-invention (не изобретай)

- Не вводи поля DTO, конфиги, зависимости, слои и архитектуру, которых нет в brief.
- Не расширяй scope: всё, что не `RW-NNN` и не `CG-NNN`, остаётся как есть.
- Не понижай и не оспаривай находки: спор с Панелью ведут Оркестратор и следующий проход Панели, не Кодер.
- Нерушимое правило слоёв: API вызывает сервис, SQL только в репозитории; Zero Auth Leak (CWE-532) соблюдается и в фиксах.

## Личный прогон

`uv run ruff check app tests`, `uv run basedpyright`, `uv run pytest tests/ -v`. Это не заменяет детерминированный CODE_GATE Оркестратора (`tools/verify_techlead_gate.py`), который перезапустит всё сам.

## Выход

1. `handoff/coder-NN.json` (NN = номер цикла, например `coder-02.json`): поля как у `feature` плюс `mode` `rework` и `rw_trace` — по записи на каждую задачу.

```text
rw_trace: [{rw_id: "RW-001", source_findings: ["F-001"],
            red_green: {red: "<команда и код>", green: "<команда и код>"},
            changed_files: ["app/services/link.py", "tests/flat_api/test_x.py"]}]
```

2. Обновлённая `.ai-team/handoff-coder.md`: сохрани разделы `Команды и коды выхода`, `Решения`, `Риски`, `Не смотрел` и добавь раздел «Что изменилось в Цикле N» (по каждой `RW-NNN`: что было, что стало, чем доказано).
3. Проверка формата: `python3 scripts/validate_handoff.py handoff/coder-NN.json`.
4. Коммит: `[agent] fix(<scope>): <описание на русском>`.
