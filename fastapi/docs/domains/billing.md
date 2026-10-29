# Доменная спецификация: Billing (Биллинг и монетизация)

## Назначение домена
Обеспечивает монетизацию сервиса коротких ссылок: списание средств за переходы по платным ссылкам, управление балансом пользователей и фиксацию истории транзакций.

## Архитектурные компоненты домена
- **Схемы данных (`app/schemas/billing.py`):**
  - `PlanType` (Enum: FREE, PRO, ENTERPRISE).
  - `WalletBalance` (баланс в копейках/центах как int для исключения ошибок округления float).
  - `ChargeRequest` / `ChargeResponse` (запрос и результат списания) — `ChargeRequest`
    дополнительно принимает `partner_metadata: dict[str, str]` (по умолчанию `{}`).
- **Контракт хранилища (`app/core/protocols.py`):**
  - `BillingRepositoryProtocol` (интерфейс `get_wallet`, `update_balance`, `record_transaction`, `list_transactions`).
- **Сервисный слой (`app/services/billing.py`):**
  - `BillingService` (методы `charge_click(user_id, link_id)`, `top_up(user_id, amount)`, `get_charge_audit(user_id)`).
- **HTTP Контроллер (`app/api/billing.py`):**
  - `POST /billing/wallets/top-up` (пополнение), `POST /billing/charges/click` (списание за клик), `GET /billing/charges/audit/{user_id}` (аудит списаний).

## Связи с другими доменами
- **Core:** хранилище баланса обязано реализовывать `BillingRepositoryProtocol` из `app/core/protocols.py`.
- **Links:** списание привязано к переходам по платным ссылкам (`link_id` из домена Links).
- **Analytics:** агрегированные метрики кликов служат источником событий списания.
- **API:** контроллер `app/api/billing.py` работает только со схема́ми `app/schemas/billing.py`.

## Инварианты безопасности биллинга
1. Баланс хранится строго в целочисленном типе (`int`, минимальная неделимая единица валюты).
2. Запрещены отрицательные балансы при списании (HTTP 402 Payment Required при нехватке средств).
3. Операция списания идемпотентна: повторный запрос с тем же `transaction_id` не приводит к повторному списанию.
4. Тарифы ограничены enum'ом `PlanType`: тарифы за пределами списка не проходят валидацию.
5. Zero Auth Leak (CWE-532): `partner_metadata` сохраняется только в журнале транзакций;
   он не логируется и не попадает в сообщения ответов. В аудите
   (`GET /billing/charges/audit/{user_id}`, DTO `ChargeAuditEntry`, сервис
   `BillingService.get_charge_audit`) всегда отдаются маскированные значения:
   `partner_metadata` содержит только `'***'` по всем ключам, а `redacted_keys`
   перечисляет ключи, чьи исходные значения были скрыты. Сырые значения доступны
   только в журнале транзакций репозитория.
6. Идемпотентность изолируется по владельцу: `transaction_id`, уже обслуженный
   другим `user_id`, отвечает нейтрально (`success=True`) с балансом вызывающего
   пользователя и не раскрывает чужой `remaining_balance`.
7. Расширения Data Contract всегда отражаются в этой карточке (правило Filing Back).

## Аудит списаний: контракт и ограничения учебного контура
- `ChargeAuditEntry`: `user_id`, `transaction_id`, `amount`, `status`,
  `remaining_balance`, `partner_metadata` (значения маскированы `'***'`),
  `redacted_keys` (ключи со скрытыми исходными значениями), `created_at`
  (фактический timestamp фиксации транзакции; в in-memory репозитории —
  момент `record_transaction`).
- `GET /billing/charges/audit/{user_id}` в учебном контуре не имеет
  auth-субъекта запроса: авторизация cross-user чтения (совпадение
  запрошенного `user_id` с субъектом запроса) в этом слайсе не реализована
  и остаётся ограничением окружения. Гарантируется только изоляция данных
  по владельцу в журнале (`list_transactions` фильтрует по `user_id`) и
  нераскрытие чужого баланса идемпотентным ретраем (инвариант 6).
  Расширение auth-инфраструктурой — отдельная карточка, не часть учебного слайса.

## Квота активных ссылок (REQ-EARS-07 / REQ-BILL-09)
- Лимит FREE: `FREE_LINK_LIMIT = 10` активных ссылок (`app/schemas/billing.py`).
  Планы PRO/ENTERPRISE — без лимита (проверка проходит всегда).
- **Сервисный слой (`BillingService`):**
  - `get_link_quota(user_id)` — снимок `PlanQuotaInfo(plan, active_links, limit, exceeded)`;
    нет кошелька → `WalletNotFoundError`.
  - `assert_link_quota(user_id)` — при превышении FREE → `QuotaExceededError`
    с нейтральным сообщением без приватных данных (Zero Auth Leak).
  - `register_link_creation(user_id)` — проверка до регистрации; при отказе
    `repo.register_new_link` не вызывается.
  - `release_link(user_id)` — снятие ссылки с учёта при disable; без исключений.
- **HTTP-гварды (`app/api/billing.py`):**
  - `apply_link_quota_guard` — вызывается в созданиях ссылок
    (`POST /links` и `POST /api/v1/links`) до фактического создания;
    превышение → HTTP 403 с телом `QuotaExceededResponse(plan, limit, active_links)`;
    неизвестный пользователь → HTTP 404.
  - `release_link_quota_guard` — вызывается в disable-хендлерах, когда
    пользователь известен.
- **Header `X-User-Id`**: опциональный заголовок в create- и disable-эндпоинтах;
  по нему определяется владелец для проверки квоты.
- **Опциональность (учебный контур):** без `X-User-Id` ссылка анонимная и
  квота не проверяется — старый путь полностью сохранён.
- **Ограничение контура:** реестр активных ссылок живёт в
  `InMemoryBillingRepository` (`active_links`), т.е. квота специфична для
  учебного хранилища; persistence — вне слайса.

## Location (расположение в коде)
- `app/schemas/billing.py` — DTO (`PlanType`, `WalletBalance`, `TopUpRequest`, `ChargeRequest`, `ChargeResponse`, `ChargeAuditEntry`, `ChargeAuditResponse`).
- `app/services/billing.py` — бизнес-логика (`charge_click(user_id, link_id)`, `top_up(user_id, amount)`).
- `app/services/payment_adapters.py` — адаптеры внешних платёжных шлюзов.
- `app/api/billing.py` — HTTP-контроллеры (`POST /billing/wallets/top-up`, `POST /billing/charges/click`, `GET /billing/charges/audit/{user_id}`).
- `app/core/protocols.py` — контракт `BillingRepositoryProtocol`.
