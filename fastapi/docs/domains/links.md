# Доменная спецификация: Links (Управление ссылками)

## Назначение домена
Обеспечивает жизненный цикл коротких ссылок: генерация уникальных хеш-идентификаторов, сохранение соответствия длинного URL, выполнение редиректов и фиксация статистики кликов.

## Архитектурные компоненты
Файлы `app/schemas/links.py`, `app/services/links.py` и `app/api/links.py` — плоские
фасады над реальными модулями `app/schemas/link.py`, `app/services/link.py` и
`app/api/v1/endpoints/links.py`.

- **Схемы данных (`app/schemas/links.py`):**
  - `LinkCreate` (URL, кастомный код, срок жизни).
  - `LinkResponse` (полная информация о ссылке), `LinkStats` (счётчик переходов).
  - `LinkBulkCreateRequest` / `LinkBulkCreateResponse` (массовое создание).
- **Сервисный слой (`app/services/links.py`):**
  - `LinkService` (методы `create_link`, `resolve_link`, `get_stats`, `disable_link`,
    `enable_link`, `bulk_create_links`).
- **HTTP Контроллер (`app/api/links.py`, префикс `/api/v1/links`):**
  - `POST /api/v1/links` (создание ссылки; тело принимает `original_url`, `target_url` или `url`).
  - `GET /api/v1/links` (список ссылок).
  - `GET /api/v1/links/{short_code}` (редирект 307 Temporary Redirect).
  - `GET /api/v1/links/{short_code}/stats` (статистика).
  - `POST /api/v1/links/{short_code}/disable` и `/enable` (управление активностью).
  - `POST /api/v1/links/bulk` (массовое создание).
- **Плоские маршруты (`app/api/routes.py` и `app/main.py`):** `POST /links`, `GET /links`, `GET /links/{code}`,
  `POST /links/{code}/disable|enable`, редирект `GET /{code}` (`307`, `404 Link disabled` / `404 Link not found`).

## Связи с другими доменами
- **Core:** использует SSRF-валидацию (`app/core/security.py`) и `generate_short_code`.
- **Analytics:** фиксирует клики через `app/services/analytics.py` при редиректе.
- **Billing:** при переходе по платной ссылке списание идёт через `POST /billing/charges/click`.
- **API:** контроллеры `app/api/v1/endpoints/links.py` работают только со схема́ми `app/schemas/`.

## Инварианты
1. Валидация URL происходит строго на уровне Pydantic-схемы (SSRF-защита из `app/schemas/validators.py`).
2. Статистика кликов — в `app/services/analytics.py`; списание за клик — `POST /billing/charges/click` (`docs/domains/billing.md`).
3. Управление транзакциями ссылок — только в `app/services/link.py`; контроллеры не содержат бизнес-логики.

## Location (расположение в коде)
- `app/schemas/link.py` — DTO (`LinkCreate`, `LinkResponse`, `LinkStats`, bulk-контракты; фасад `app/schemas/links.py`).
- `app/services/link.py` — бизнес-логика жизненного цикла (фасад `app/services/links.py`).
- `app/repositories/link_repository.py` — доступ к БД (фасад `app/repositories/link.py`).
- `app/api/v1/endpoints/links.py` — HTTP-контроллеры под префиксом `/api/v1/links` (фасад `app/api/links.py`).
- `app/api/v1/router.py` — регистрация роутера; плоские маршруты — `app/api/routes.py` и `app/main.py`.
- `app/domain/link.py`, `app/domain/value_objects.py` — доменные модели и ошибки.
