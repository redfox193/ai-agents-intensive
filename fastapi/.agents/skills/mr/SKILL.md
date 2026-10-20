---
name: mr
description: >
  Готовит Merge Request: автофиксы, актуальная ветка, зелёные проверки, описание,
  Jira-ссылка и чеклист перед отправкой. Звать после завершения реализации перед
  созданием или обновлением MR. НЕ для code review (code-review.md) и разработки
  фичи (feature.md).
owner: tbd
freedom: strict
last_reviewed: 2026-08-09
---

# Skill: Merge Request

## Алгоритм подготовки MR

### 1. Перед созданием MR
- Прочитать `.agents/agents/mr.md` — требования к оформлению.
- Прогнать автофиксы: `uv run ruff format . && uv run ruff check --fix .`.
- Убедиться что все проверки проходят: `uv run ruff check . && uv run basedpyright && uv run pytest -q`.
- Проверить что ветка актуальна: `git fetch origin main && git rebase origin/main`.

### 2. Описание MR
- Заголовок: тип + краткое описание (`feat: add link update endpoint`).
- Тело: что изменено, зачем, как проверить.
- Указать Jira-задачу.

### 3. Чеклист перед отправкой
- Нет закомментированного кода.
- Нет `print()` для отладки.
- Нет лишних файлов в коммите.
- Все новые эндпоинты покрыты тестами.
- Если изменена схема БД — есть Alembic migration.
