SEAT: judge-1
ROUND: D1
HAT: Реалист
PROCEDURE_ACCEPTED: fec2a3657f4a3fbca4c46fc1fc60ff7d03aa3157a197e4e904e006c2923961cf
ORIGIN: reference-fixture

## Ответы на вопросы коллег
- вопросов не было
POSITION F-001: AMEND | severity=MINOR | NEW: StripePaymentGateway нигде не создаётся в приложении: единственные ссылки на него — tests/unit/test_protocol_conformance.py:5 и :33, а process_external_charge не вызывается ни из app/api, ни из app/services; подключения к DI нет (app/api/deps.py:12-20 выдаёт только LinkService), поэтому утечка токена в рантайме LINK-42 недостижима
POSITION F-002: WITHDRAW | NEW: app/schemas/link.py:15-19 вызывает validate_target_url_security при создании ссылки (app/schemas/validators.py:40-51: только http и https, внутренние хосты запрещены), поэтому в БД попадают проверенные адреса и редирект по сохранённому значению не открывает новый вектор
POSITION F-003: AGREE | evidence: tests/flat_api/test_link_toggle.py:46-51 проверяет только подстроку secret-auth-key
POSITION F-004: DISPUTE | evidence: проверка link.disabled в read_link (app/api/routes.py:36-37) читает поле уже загруженной модели без SQL и транзакций; спека §5.1 запрещает в хэндлерах прямой SQL и операции с транзакциями, а не чтение поля; поведение закреплено tests/flat_api/test_link_toggle.py:26
## Вопросы коллегам (к следующему раунду)
- judge-3: чем закреплено 404 для отключённой ссылки в GET /links/{code} — тестом или требованием спеки?
