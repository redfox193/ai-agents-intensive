# Дорожная карта приёмки домена Billing (волны проверки)

- [x] **Волна 1: Schemas** — Проверка `app/schemas/billing.py` (Pydantic v2) требованиями EARS.
- [x] **Волна 2: Core Protocols** — Проверка `BillingRepositoryProtocol` в `app/core/protocols.py` и границ слоёв.
- [x] **Волна 3: Services** — Проверка `app/services/billing.py`, бюджета Blast Radius и юнит-тестов.
- [x] **Волна 4: API Routers** — Проверка `app/api/billing.py` и интеграционных тестов.
- [x] **Финал: Techlead Gate** — Прогон всех линтеров и верификаторов (exit 0).
