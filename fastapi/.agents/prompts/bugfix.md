# Bugfix

---

## Вариант A — субмодуль в проекте (`.agents/`)

```text
Jira: <JIRA-KEY>
Дефект: <одна строка — что ломается и как проявляется>
Ветка bugfix/<JIRA-KEY>-<slug>. Действуй по .agents/skills/bugfix.md.

DONE: красный→зелёный regression; гейт из skill; коммит [agent]. В ответе: красный тест, diff, итог гейта.
```

---

## Вариант B — запуск из ai-sdlc-rules напрямую

```text
Jira: <JIRA-KEY>
Дефект: <одна строка — что ломается и как проявляется>
Ветка bugfix/<JIRA-KEY>-<slug>. Действуй по skills/bugfix.md.

DONE: красный→зелёный regression; гейт из skill; коммит [agent]. В ответе: красный тест, diff, итог гейта.
```
