# Hotfix

Срочный фикс в прод. Минимальный скоуп — только то что нужно для фикса.

---

## Вариант A — субмодуль в проекте (`.agents/`)

```text
Jira: <JIRA-KEY>
Инцидент: <что упало в проде, как проявляется>
Ветка hotfix/<JIRA-KEY>-<slug> от main. Действуй по .agents/skills/hotfix.md.

DONE: минимальный scope; regression в том же коммите; гейт из skill; коммит [agent].
```

---

## Вариант B — запуск из ai-sdlc-rules напрямую

```text
Jira: <JIRA-KEY>
Инцидент: <что упало в проде, как проявляется>
Ветка hotfix/<JIRA-KEY>-<slug> от main. Действуй по skills/hotfix.md.

DONE: минимальный scope; regression в том же коммите; гейт из skill; коммит [agent].
```
