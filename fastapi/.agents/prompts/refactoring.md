# Рефакторинг

Поведение не меняется. Только структура кода.

---

## Вариант A — субмодуль в проекте (`.agents/`)

```text
Jira: <JIRA-KEY>
Рефакторинг: <что и зачем меняем>
Ветка refactor/<JIRA-KEY>-<slug>. Действуй по .agents/skills/refactoring.md.

DONE: поведение то же; гейт из skill; коммит [agent].
```

---

## Вариант B — запуск из ai-sdlc-rules напрямую

```text
Jira: <JIRA-KEY>
Рефакторинг: <что и зачем меняем>
Ветка refactor/<JIRA-KEY>-<slug>. Действуй по skills/refactoring.md.

DONE: поведение то же; гейт из skill; коммит [agent].
```
