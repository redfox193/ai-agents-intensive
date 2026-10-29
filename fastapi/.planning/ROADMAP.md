# Дорожная карта free-plan-link-limit-v3 (BILL-FREE01)

- [x] **Волна 1: Schemas/Domain** — `app/schemas/billing.py` (+ доменные ссылки limit-контракты: QuotaError-схема/DTO ответа; максимум 2 файла) + юнит-тесты схемы.
- [x] **Волна 2: Core Protocols** — `app/core/protocols.py` (только контракты для лимита: repo count/is_active через протокол; максимум 2 файла); границы слоёв.
- [x] **Волна 3: Services** — `app/services/link.py`/`app/services/billing.py`: проверка квоты FREE (10) в создании активной ссылки; юнит-тесты red→green.
- [x] **Волна 4: API Routers** — `app/api/v1/endpoints/links.py` / `app/api/billing.py`: HTTP 403 на доменное превышение квоты; integration-тест.
- [x] **Финал: Techlead Gate** — verify_techlead_gate.py ACCEPTED + Filing Back в docs/domains/billing.md.
