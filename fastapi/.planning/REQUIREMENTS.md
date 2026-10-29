# Требования к домену Billing (v3: free-plan-link-limit)

1. [REQ-BILL-01] Поддержка тарифных планов FREE, PRO, ENTERPRISE (`PlanType`).
2. [REQ-BILL-02] Целочисленный баланс (int), отсутствие отрицательного баланса.
3. [REQ-BILL-03] Идемпотентность списания по `transaction_id` (min_length 16).
4. [REQ-BILL-04] Нехватка средств → HTTP 402.
5. [REQ-BILL-05] Изоляция слоёв: schemas -> core -> services -> api.
6. [REQ-BILL-06] Контракт `partner_metadata: dict[str, str]` + маскирование в аудите (Zero Auth Leak, CWE-532).
7. [REQ-BILL-07] Идемпотентность изолирована по владельцу.
8. [REQ-BILL-08] Аудит списаний `GET /billing/charges/audit/{user_id}`; ограничение учебного контура задокументировано.
9. [REQ-BILL-09 NEW] ПОКА план пользователя FREE, система ДОЛЖНА ограничивать число его активных ссылок до 10; превышение → доменная ошибка → HTTP 403 `PlanQuotaExceeded`; PRO/ENTERPRISE — без лимита (REQ-EARS-07 косвенно).

Out of scope: тарифные переходы, PRO/лимиты, auth-инфраструктура, пагинация, PDF/webhook/промo.

Нерушимые правила: замороженное ядро (config/security/main); бюджет ≤ 7 файлов; Filing Back; aio Kontroller of business rules — services только.
