# Оркестрация Coder → Reviewer → Summarizer

## Вариант A — субмодуль в проекте (`.agents/`)

```text
Задача: <одна строка>
Действуй по .agents/skills/orchestrate-coder-reviewer-summarizer.md.
Модели ролей — из таблицы в skill. Всё сам. git push / PR не делай.
final_gate_council=false.
Summarizer: claim_ledger (каждый bullet → evidence_span в файле).
```

## Вариант B — запуск из ai-sdlc-rules

```text
Задача: <одна строка>
Действуй по skills/orchestrate-coder-reviewer-summarizer.md.
Модели ролей — из таблицы в skill. Всё сам. git push / PR не делай.
final_gate_council=false.
Summarizer: claim_ledger (каждый bullet → evidence_span в файле).
```
