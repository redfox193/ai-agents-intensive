# Юнит-тесты

---

## Вариант A — субмодуль в проекте (`.agents/`)

```text
Ветка test/<slug>-unit (main чистая, иначе СТОП).
Unit-тесты для <файл сервиса>: <сценарии>. Действуй по .agents/skills/tests-unit.md.

DONE: 100% coverage модуля; гейт из skill; reviews/<slug>-coverage.md; коммит [agent].
```

---

## Вариант B — запуск из ai-sdlc-rules напрямую

```text
Ветка test/<slug>-unit (чистое дерево, иначе СТОП).
Unit-тесты для <файл сервиса>: <сценарии>. Действуй по skills/tests-unit.md.

DONE: 100% coverage модуля; гейт из skill; reviews/<slug>-coverage.md; коммит [agent].
```
