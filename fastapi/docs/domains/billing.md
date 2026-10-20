# Доменная спецификация: Billing (Биллинг и монетизация)

## Назначение домена
Обеспечивает монетизацию сервиса коротких ссылок: списание средств за переходы по платным ссылкам, управление балансом пользователей и фиксацию истории транзакций.

## Архитектурные компоненты домена
- **Схемы данных (`app/schemas/billing.py`):**
  - `PlanType` (Enum: FREE, PRO, ENTERPRISE).
  - `WalletBalance` (баланс в копейках/центах как int для исключения ошибок округления float).
  - `ChargeRequest` / `ChargeResponse` (запрос и результат списания).
- **Контракт хранилища (`app/core/protocols.py`):**
  - `BillingRepositoryProtocol` (интерфейс `get_wallet`, `update_balance`, `record_transaction`).
- **Сервисный слой (`app/services/billing.py`):**
  - `BillingService` (методы `charge_click(user_id, link_id)`, `top_up(user_id, amount)`).
- **HTTP Контроллер (`app/api/billing.py`):**
  - `POST /billing/wallets/top-up` (пополнение).
  - `POST /billing/charges/click` (списание за клик).

## Инварианты безопасности биллинга
1. Баланс хранится строго в целочисленном типе (`int`, минимальная неделимая единица валюты).
2. Запрещены отрицательные балансы при списании (HTTP 402 Payment Required при нехватке средств).
3. Операция списания идемпотентна: повторный запрос с тем же `transaction_id` не приводит к повторному списанию.
