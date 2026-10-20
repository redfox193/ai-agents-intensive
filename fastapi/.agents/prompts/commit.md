# Коммит

Один промт для любого типа задачи — feature, bugfix, hotfix, refactor.

**Формат сообщения**:

- Префикс — `[agent]` / `[assisted]` / `[manual]` (английский маркер).
- Тэг Conventional Commits — `feat:` / `fix:` / `refactor:` / `chore:` / `docs:` / `test:` / `perf:` (английский).
- Scope в скобках, например `(api)`, `(services)`, `(deps)` — английский.
- **Описание после двоеточия — на русском.**

Пример: `[agent] feat(api): добавить эндпоинт PATCH /links/{id}`

---

## Вариант A — субмодуль в проекте (`.agents/`)

```text
Сделай один git commit текущих изменений.
Правила из .agents/AGENTS.md: префикс [agent] / [assisted] / [manual],
затем Conventional Commits (feat: / fix: / refactor: / chore:).
Описание после двоеточия — на русском.

Порядок:
1. git diff — посмотри что изменилось.
2. git add <нужные файлы> — не добавляй лишнего.
3. git commit -m "[agent] <type>(<scope>): <описание на русском>"
4. git log -1 --stat — покажи результат.

Если pre-commit хук упал с автофиксом (ruff format, trailing-whitespace):
git add <исправленные файлы> && git commit повторно.
Если хук упал с реальной ошибкой — исправь её, не обходи хук.
```

---

## Вариант B — запуск из ai-sdlc-rules напрямую

```text
Сделай один git commit текущих изменений в проекте <путь к репозиторию>.
Правила из AGENTS.md: префикс [agent] / [assisted] / [manual],
затем Conventional Commits (feat: / fix: / refactor: / chore:).
Описание после двоеточия — на русском.

Порядок:
1. git diff — посмотри что изменилось.
2. git add <нужные файлы> — не добавляй лишнего.
3. git commit -m "[agent] <type>(<scope>): <описание на русском>"
4. git log -1 --stat — покажи результат.

Если pre-commit хук упал с автофиксом (ruff format, trailing-whitespace):
git add <исправленные файлы> && git commit повторно.
Если хук упал с реальной ошибкой — исправь её, не обходи хук.
```
