# Доменная спецификация: Core & Security

## Назначение домена
Обеспечивает базовую инфраструктуру монолита: загрузку настроек из окружения, валидацию конфигураций, генерацию и верификацию токенов безопасности, а также регистрацию структурных протоколов интерфейсов.

## Архитектурные компоненты
- **Конфигурация (`app/core/config.py`):**
  - Класс `Settings` на базе `pydantic_settings.BaseSettings`: `DATABASE_URL`, `BASE_URL`, `CODE_LENGTH`, `API_V1_PREFIX`, `APP_ENV` (из окружения и `.env`).
  - Заморожен от неконтролируемых модификаций агентами.
- **Безопасность (`app/core/security.py`):**
  - Функция `validate_target_url_security` и исключение `SecuritySSRFError`: защита от SSRF
    при приёме целевых URL; `validate_target_url` и `generate_short_code` — помощники доменного слоя.
- **Логирование (`app/core/logging.py`):**
  - Структурный `logger` и `setup_logging`.
- **Протоколы интерфейсов (`app/core/protocols.py`):**
  - Абстрактные контракты `typing.Protocol` для репозиториев и платежных шлюзов.
  - Позволяет изолировать сервисный слой от конкретных СУБД.

## Связи с другими доменами
- **Links:** предоставляет SSRF-валидацию `original_url` и генерацию `short_code` при создании ссылок.
- **Analytics:** не зависит от него напрямую; агрегаты формируются в `app/services/analytics.py`.
- **Billing:** определяет контракт хранилища `BillingRepositoryProtocol` в `app/core/protocols.py`.
- **API:** все слои импортируют только core и schemas; обратных импортов нет.

## Инварианты
1. Модули ядра никогда не импортируют код из `app/services/` или `app/api/`.
2. Изменение `Settings` требует явного одобрения владельца через Codeowners.
3. Публичные контракты объявляются только через `typing.Protocol` и не зависят от реализаций.

## Location (расположение в коде)
- `app/core/config.py` — настройки окружения (`app/config.py` — плоский фасад).
- `app/core/security.py` — SSRF-защита и валидация URL.
- `app/core/logging.py` — структурное логирование.
- `app/core/protocols.py` — протоколы интерфейсов и платежных шлюзов.
