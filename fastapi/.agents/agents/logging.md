# Logging rules

## Стек

- **Сервис** — `structlog` (структурные логи).
- **Библиотека** — стандартный `logging` (не навязываем формат потребителю).
- Сериализатор — `structlog.processors.JSONRenderer()`: он работает из коробки на stdlib `json`, дополнительных зависимостей не требует. `orjson` (`JSONRenderer(serializer=orjson.dumps)`) — опциональное ускорение для prod: нужен `uv add orjson`, и он отдаёт `bytes` — это учитывается в logger factory.
- Конфигурация — один раз на старте, в `configure_logging()` из `app/logging.py`.

## Правила

- **Никогда `print()`** для логирования. Отлаживаешь — `breakpoint()`; пишешь в стрим — `logger.info(...)`.
- **kwargs, не f-строки** в сообщении. Event-строка стабильная, параметры отдельно:

  ```python
  # ❌
  logger.info(f"order {order_id} processed in {duration}s")

  # ✅
  logger.info("order processed", order_id=order_id, duration_s=duration)
  ```

  Иначе в Loki / ELK невозможно сгруппировать `count by event` — каждое сообщение уникальное.

- **Не логируй секреты в kwargs.** Пароли, токены, Authorization, cookie, PII — никогда. На последней линии работает рекурсивный `redact_secrets`-processor (см. `app/logging.py`), но это страховка; имя поля `password` / `token` / `secret` в `logger.info(..., password=p)` уже **bug в код-стиле**.
- **Не логируй в горячих циклах.** Лог в hot path под нагрузкой → I/O bottleneck. Логируй итог цикла или сэмплируй (один из N).
- **Контекст запроса — через `bind_contextvars`.** Middleware биндит `request_id` (или подхватывает `X-Request-ID`) в начале запроса, очищает в конце. Все логи в рамках запроса автоматически получают это поле — `grep request_id=...` показывает весь pipeline.

## Уровни

| Уровень | Когда | Пример |
|---|---|---|
| `debug` | Локальная отладка; в prod отключено | `log.debug("repo query plan", plan=plan)` |
| `info` | Значимые события: запуск, бизнес-операция | `log.info("link created", code=code)` |
| `warning` | Нештатно, но обработано (retry, fallback) | `log.warning("agentplatform retry", attempt=2)` |
| `error` | Операция не выполнена, требует внимания | `log.error("db connection failed", url=...)` |
| `critical` | Сервис неработоспособен | `log.critical("config missing", key="DB_URL")` |

В prod уровень `info` и выше; `debug` включается локально через ENV (`LOG_LEVEL=DEBUG`).

## Формат

- **prod** — JSON-строки (`JSONRenderer()`, при желании с `serializer=orjson.dumps`), одна строка = один event. Это требование Loki / ELK / Datadog.
- **dev** (`APP_ENV=local`) — `ConsoleRenderer` с цветом, читаемые traceback'и.
- Поле `message` — переименованный `event` (для совместимости с Loki, где `message` — стандартное имя).
- Поле `request_id` — добавляется автоматически в middleware (см. `app/middleware/request_id.py`).
- Поля `module` / `func_name` / `lineno` — добавляются автоматически через `CallsiteParameterAdder`.

## Интеграция со stdlib logging

Логи `uvicorn` / `sqlalchemy` / `fastapi` / `httpx` идут через стандартный `logging`. Чтобы они **тоже** проходили через redact_secrets и попадали в один JSON-поток, в `configure_logging()` настраивается `structlog.stdlib.ProcessorFormatter` + `foreign_pre_chain`. Без этого SQL-запросы от SQLAlchemy и HTTP-логи uvicorn летят сырыми и могут утечь параметрами в plaintext.

## Запреты (блокируют merge)

- `print()` в `app/` для логирования.
- `logger.info(f"... {var} ...")` — f-строка в сообщении.
- Поля `password` / `token` / `secret` / `authorization` / `cookie` / `api_key` в kwargs логгера.
- Свой `logging.basicConfig(...)` в обход `configure_logging()`.
