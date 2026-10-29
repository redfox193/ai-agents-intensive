# Индекс архитектуры и доменов монолита fastapi-linksvc

> **Версия архитектуры:** 2.4.0
> **Инвариант слоев:** schemas -> core -> services -> api (обратные импорты запрещены!)
> **Бюджет задачи:** ≤ 7 файлов изменений, ≤ 400 строк добавления.
> **Единое приложение:** `app/` и `alembic/` одинаковы в Днях 1-3; День 3 добавляет скилы и верификаторы.

## Слои приложения

| Слой | Назначение | Репрезентативные модули |
|---|---|---|
| **Схемы (DTO)** | Pydantic-контракты DTO и валидаторы входных данных | `app/schemas/link.py`, `app/schemas/analytics.py`, `app/schemas/billing.py`, `app/schemas/validators.py` |
| **Core (ядро)** | Конфигурация, логирование, SSRF-защита URL, протоколы интерфейсов | `app/core/config.py`, `app/core/logging.py`, `app/core/security.py`, `app/core/protocols.py` |
| **Domain** | Доменные модели, value objects, ошибки | `app/domain/link.py`, `app/domain/value_objects.py`, `app/domain/errors.py` |
| **DB** | SQLAlchemy-модели и сессии БД | `app/db/models.py`, `app/db/session.py`, `app/db/base.py` |
| **Repositories** | Доступ к БД и работе с внешними API | `app/repositories/link_repository.py`, `app/repositories/analytics.py` |
| **Services** | Бизнес-логика и управление транзакциями | `app/services/links.py`, `app/services/analytics.py`, `app/services/billing.py`, `app/services/payment_adapters.py` |
| **API** | FastAPI-роутеры, схемы поверх DTO, обработчики ошибок | `app/api/routes.py`, `app/api/v1/router.py`, `app/api/errors.py`, `app/api/deps.py` |

## Карта функциональных доменов

| Домен | Зона ответственности | Ключевые файлы реализации | Спецификация |
|---|---|---|---|
| **Core & Security** | Конфигурация, логирование, SSRF-защита URL, протоколы интерфейсов | `app/core/config.py`, `app/core/security.py`, `app/core/protocols.py` | `docs/domains/core.md` |
| **Links** | Создание, редирект, включение/отключение и статистика коротких ссылок | `app/schemas/links.py`, `app/services/links.py`, `app/api/links.py` | `docs/domains/links.md` |
| **Analytics** | Журнал кликов и агрегаты: уникальные посетители, топ источников | `app/schemas/analytics.py`, `app/services/analytics.py`, `app/api/v1/endpoints/analytics.py` | `docs/domains/analytics.md` |
| **Billing** | Лицевые счета, тарифные планы, списание за клики | `app/schemas/billing.py`, `app/services/billing.py`, `app/api/billing.py` | `docs/domains/billing.md` |

## Ключевые инварианты монолита
1. Контроллеры `app/api/` принимают и возвращают только Pydantic-схемы из `app/schemas/`.
2. Вся бизнес-логика и управление транзакциями сосредоточены в `app/services/`.
3. Слой сервисов взаимодействует с БД и внешними API только через контракты `app/core/protocols.py`.
