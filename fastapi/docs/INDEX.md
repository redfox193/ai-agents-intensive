# Индекс архитектуры и доменов монолита fastapi-linksvc

> **Версия архитектуры:** 2.4.0  
> **Инвариант слоев:** schemas -> core -> services -> api (обратные импорты запрещены!)  
> **Бюджет задачи:** ≤ 7 файлов изменений, ≤ 400 строк добавления.  
> **Единое приложение:** `app/` и `alembic/` одинаковы в Днях 1-3; День 3 добавляет скилы и верификаторы.
> **Карта модулей:** `docs/module-map.md` — цепочка создания ссылки и радиус влияния правки (вход скила `small-fix`).

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
