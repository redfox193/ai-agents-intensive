# Требования к домену Billing

1. [REQ-BILL-01] Поддержка тарифных планов FREE, PRO, ENTERPRISE.
2. [REQ-BILL-02] Целочисленный баланс в минимальных единицах валюты (int).
3. [REQ-BILL-03] Идемпотентность списания по `transaction_id`.
4. [REQ-BILL-04] Запрет отрицательного баланса (HTTP 402).
5. [REQ-BILL-05] Полная изоляция слоев: schemas -> core -> services -> api.
