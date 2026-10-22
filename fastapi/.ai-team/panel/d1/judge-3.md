SEAT: judge-3
ROUND: D1
HAT: Скептик
PROCEDURE_ACCEPTED: fec2a3657f4a3fbca4c46fc1fc60ff7d03aa3157a197e4e904e006c2923961cf
ORIGIN: reference-fixture

## Ответы на вопросы коллег
- вопросов не было
POSITION F-001: AGREE | evidence: app/services/payment_adapters.py:13 пишет token в лог, дефект есть независимо от того, подключён ли адаптер
POSITION F-002: DISPUTE | evidence: app/schemas/validators.py:40-51 отсекает чужие схемы и внутренние хосты до записи в БД
POSITION F-003: AGREE | evidence: tests/flat_api/test_link_toggle.py:51 не проверяет Authorization
POSITION F-004: AGREE | evidence: app/api/routes.py:36-37 содержит бизнес-правило видимости ссылки прямо в хэндлере
## Вопросы коллегам (к следующему раунду)
- judge-1: вызывается ли StripePaymentGateway.process_external_charge где-либо вне тестов?
