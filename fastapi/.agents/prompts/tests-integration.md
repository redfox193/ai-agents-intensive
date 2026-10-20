# Интеграционные тесты

---

## Вариант A — субмодуль в проекте (`.agents/`)

```text
Ветка test/<slug>-integration (main чистая, иначе СТОП).
Integration-тесты для <эндпоинты/сценарии>. Действуй по .agents/skills/tests-integration.md.

DONE: гейт из skill; coverage области 100%; reviews/<slug>-coverage.md; коммит [agent].
```

---

## Вариант B — запуск из ai-sdlc-rules напрямую

```text
Ветка test/<slug>-integration (чистое дерево, иначе СТОП).
Integration-тесты для <эндпоинты/сценарии>. Действуй по skills/tests-integration.md.

DONE: гейт из skill; coverage области 100%; reviews/<slug>-coverage.md; коммит [agent].
```
