---
name: docs
description: >
  Документирует изменения во время задачи: ADR, docstring, CHANGELOG и README
  рядом с реализацией. Звать при изменении публичного API, архитектурного решения,
  ENV, зависимости или пользовательского поведения. НЕ для итогового документа по
  завершённой задаче (post-task-docs.md) и НЕ для PRD/планирования.
owner: tbd
freedom: guided
last_reviewed: 2026-08-09
---

# Skill: Docs

## Алгоритм документирования в рамках задачи

### 1. Перед реализацией
- Определи, затрагивает ли задача публичный API (новый эндпоинт, метод сервиса, ENV, зависимость).
- Определи, является ли решение архитектурным (несколько модулей, новый инструмент, смена подхода).
- Если архитектурное — **создай ADR до написания кода**: это заставит сформулировать Context и Decision прежде чем утонуть в реализации.

### 2. Во время реализации
- Пиши docstring одновременно с сигнатурой функции, до тела. Это выравнивает имена, параметры и ожидания.
- Формат:

```python
def create(original_url: str) -> Link:
    """Create a short link with auto-generated code.

    Args:
        original_url: Target URL. Must be a syntactically valid http/https URL.

    Returns:
        Newly created Link entity with unique short code.

    Raises:
        ValueError: If original_url is empty or not a valid http/https URL.
    """
```

### 3. После реализации
- Обнови `CHANGELOG.md` под `[Unreleased]`: выбери секцию (Added / Changed / Fixed / Removed / Security) и напиши одну строку в пользовательском стиле. Пример: `- Fixed 500 on POST /links with url > 2048 chars (PROJ-202)`.
- Если изменились: ENV-переменная, команда запуска, зависимость, список эндпоинтов — **обнови соответствующий раздел README.md**.
- Если создан ADR — добавь ссылку на него из README (в раздел Architecture).

### 4. Шаблон ADR

```markdown
# NNNN — <короткое название решения>

## Status

Accepted

## Context

<Какая проблема? Какие были ограничения, требования, силы давления на решение?>

## Decision

<Что конкретно решили. Одно-два чётких предложения.>

## Consequences

<Что станет лучше? Что станет хуже? Какие риски остались принятыми?>

## Alternatives considered

- <Альтернатива 1>: почему не выбрали.
- <Альтернатива 2>: почему не выбрали.
```
