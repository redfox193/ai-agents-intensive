# Схема panel-rework-brief.json

`handoff/panel-rework-brief.json` — передаточный документ от функции `panel-rework-summarizer` к Кодеру (скилл `rework`). Он появляется только после согласованного REJECT. Файл в `handoff/` лежит как runtime-артефакт (в git не коммитится). Один JSON-объект на корне, без пояснений и без второго объекта.

Функция не рассуждает по существу: она раскладывает находки `findings-ledger.tsv` по корзинам и пересказывает доказательства. Исправления она не изобретает, тяжесть не меняет, разные причины не склеивает.

## Поля корня (все обязательны)

| Поле | Тип | Значение |
|---|---|---|
| `schema_version` | строка | `"1.0"` |
| `task_id` | строка | например `LINK-42` |
| `cycle` | целое | номер цикла, который получит Кодер (после первого прохода — 2) |
| `source_pass_id` | строка | `pass_id` из `manifest.json` прохода-источника |
| `ledger_hash` | строка | sha256 файла `.ai-team/panel/findings-ledger.tsv` |
| `instructions` | массив | blocking-инструкции `RW-001`, `RW-002`, … |
| `non_blocking_followups` | массив | мелкие доработки `FU-001`, … (может быть пустым) |
| `excluded` | массив | находки, которые не требуют работы Кодера, с причиной |
| `findings_total` | целое | число F-ID в реестре |
| `source_findings` | массив строк | все F-ID реестра (`F-001`, …) |
| `terminal_objections` | массив объектов | возражения из C1: `judge`, `evidence`, `defect` (может быть пустым) |

## `instructions[]` (blocking)

Сюда идут находки `BLOCKER` и `IMPORTANT` со статусом `OPEN` или `AGREED`.

| Поле | Значение |
|---|---|
| `id` | `RW-001`, `RW-002`, … по порядку |
| `source_findings` | массив F-ID (минимум один), которые закрывает инструкция |
| `disposition` | всегда `"blocking"` |
| `criterion` | номер критерия рубрики, целое 1..5 |
| `file` | относительный путь файла |
| `line_hint` | строка или целое: `42` или `"84-102"` |
| `rule_ref` | на какое правило опирается (спека, рубрика, `AGENTS.md`) |
| `action` | что сделать, по существу находки реестра, без новых идей |
| `acceptance` | команда или бинарный оракул, по которому Кодер и Оркестратор проверят исправление |
| `source` | кто и в каком раунде нашёл (например, `judge-1 / R1`) |
| `evidence` | цитата или ссылка `file:line` из файлов раундов |

## `non_blocking_followups[]`

Находки `MINOR` (`AGREED` или `OPEN`). Поля: `id` (`FU-001`, …), `source_findings`, `evidence`, `action`, `acceptance`. Кодер выполняет их по возможности, и они не блокируют приёмку.

## `excluded[]`

Находки, не требующие работы Кодера. Поля: `source_finding` (один F-ID), `evidence`, `reason`. Закрытый список причин:

| `reason` | Когда |
|---|---|
| `duplicate_of:F-NNN` | дубль другой находки; цель существует в реестре, не сама эта находка, циклов нет |
| `invalid_after_recheck` | находка снята (`WITHDRAWN`) или опровергнута проверкой |
| `out_of_scope` | вне Blast Radius задачи |
| `foreign_key` | чужая задача или чужой ключ |

Статус `WITHDRAWN` всегда попадает в `excluded` с причиной `invalid_after_recheck`. Любое другое значение `reason` недопустимо.

## Полное непересекающееся покрытие

- Объединение F-ID трёх корзин (`instructions[].source_findings`, `non_blocking_followups[].source_findings`, `excluded[].source_finding`) равно `source_findings`, а оно равно множеству F-ID реестра.
- Каждый F-ID встречается ровно один раз во всех корзинах вместе: ни пропусков, ни дублей, ни F-ID вне реестра.
- `findings_total` равно числу строк реестра без заголовка.
- Отсева «топ-N», отсрочки и склейки разных причин нет.

## Привязка и потребитель

- `ledger_hash` связывает бриф с конкретным реестром. Если реестр пересобран и sha256 не совпал, бриф недействителен.
- `terminal_objections` переносит `OBJECTION` из C1 дословно. Эти возражения не имеют F-ID, поэтому не попадают в корзины; Кодер учитывает их как контекст.
- Потребитель — скилл `rework`: Кодер получает бриф как основной список blocking-работ. В `handoff/coder-NN.json` (режим `rework`) на каждую инструкцию `RW-NNN` должна быть запись в `rw_trace` с `source_findings` и парой `red_green`.

## Проверка

```bash
python3 scripts/validate_handoff.py handoff/panel-rework-brief.json
```

Скрипт проверяет обязательные поля и типы, форматы `RW-NNN`/`FU-NNN`/`F-NNN`, закрытый список `reason`, полноту и непересечение покрытия, `findings_total`, а с флагом `--ledger` ещё и совпадение с реальным реестром. При успехе функция `panel-rework-summarizer` печатает `VALID n_instructions=N`; при невалидном файле Кодер не стартует и Оркестратор эскалирует.

## Пример

```json
{
  "schema_version": "1.0", "task_id": "LINK-42", "cycle": 2, "source_pass_id": "pass-001",
  "ledger_hash": "<sha256 findings-ledger.tsv>",
  "instructions": [
    {"id": "RW-001", "source_findings": ["F-001"], "disposition": "blocking", "criterion": 5,
     "file": "app/services/link.py", "line_hint": 42, "rule_ref": "docs/gate-rubric.md",
     "action": "Убрать target_url из лога", "acceptance": "uv run pytest tests/flat_api -q",
     "source": "judge-1 / R1", "evidence": "app/services/link.py:42"}
  ],
  "non_blocking_followups": [
    {"id": "FU-001", "source_findings": ["F-002"], "evidence": "docs/risk-plan-LINK-42.md:10",
     "action": "Уточнить формулировку", "acceptance": "ручная сверка риск-плана"}
  ],
  "excluded": [{"source_finding": "F-003", "evidence": "d2/judge-2.md",
                "reason": "invalid_after_recheck"}],
  "findings_total": 3, "source_findings": ["F-001", "F-002", "F-003"],
  "terminal_objections": []
}
```
