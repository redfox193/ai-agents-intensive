# Спецификация задачи LINK-42: Управление активностью коротких ссылок

> **Единая кодовая база.** Приложение `linksvc` едино для трёх дней и доступно уже в Дне 1:
> функциональность LINK-42 в нём присутствует. День 2 отрабатывает **процесс** (спека → Coder →
> Reviewer → Gate): конвейер принимает эту реализацию и доказывает её командами и мутационной
> проверкой. Пути ниже — слои единого приложения.

## 1. Метаданные и Blast Radius (Радиус изменений)
- **ID задачи:** LINK-42
- **Тип изменения:** Новая функциональность (Feature) с сохранением обратной совместимости
- **Ветка git:** `feature/LINK-42-enable-link`
- **Разрешённые файлы для изменения:**
  - `app/models/link.py` (поле активности ссылки `disabled`)
  - `app/main.py` (редирект `GET /{code}`), `app/api/routes.py` (эндпоинты деактивации/активации)
  - `app/services/link.py` (правило перехода по ссылке: активна, отключена, не найдена)
  - `app/repositories/link.py` (запросы чтения и обновления статуса активности, атомарный счётчик кликов)
  - `alembic/versions/` (миграции схемы БД для полей `disabled` и `clicks`)
  - `tests/flat_api/test_link_toggle.py`, `tests/flat_api/test_links.py` (тесты контракта LINK-42)
  - `alembic.ini` и `alembic/env.py` — инфраструктура стартового состояния Дня 2, не часть правки
- **СТРОГО ЗАПРЕЩЕНО ТРОГАТЬ:**
  - `tests/flat_api/test_characterization.py` (защитный слепок поведения Дня 1 — ломать нельзя!)
  - `app/db/session.py` (конфигурация подключения к базе данных)
  - `AGENTS.md` (правила репозитория неизменны)
  - Любые файлы вне каталогов `app/`, `tests/`, `specs/`, `.ai-team/`

## 2. Бизнес-требования и машина состояний
1. Каждая создаваемая ссылка по умолчанию является **активной** (`disabled: False`).
2. Владелец ссылки может временно деактивировать её вызовом `POST /links/{code}/disable`.
3. Владелец ссылки может повторно активировать её вызовом `POST /links/{code}/enable`.
4. При попытке перехода по отключенной ссылке (`GET /{code}`):
   - Сервис обязан возвращать HTTP статус `404 Not Found` с телом `{"detail": "Link disabled"}` (или `"Link not found"`).
   - Счетчик переходов ссылки инкрементироваться НЕ должен.
5. Повторный вызов `disable` на уже отключенной ссылке или `enable` на активной ссылке является идемпотентным (возвращает HTTP 200 с текущим состоянием).
6. Если ссылка с указанным `code` не существует, эндпоинты `disable` и `enable` возвращают HTTP `404 Not Found` с телом `{"detail": "Link not found"}`.

## 3. Контракты интерфейсов (API & DTO)
### 3.1. Эндпоинт деактивации
- **Метод и путь:** `POST /links/{code}/disable`
- **Заголовки:** Опциональный токен авторизации (Bearer token)
- **Успешный ответ (HTTP 200 OK):**
```json
{
  "short_code": "demo123",
  "target_url": "https://example.com",
  "disabled": true
}
```

### 3.2. Эндпоинт активации
- **Метод и путь:** `POST /links/{code}/enable`
- **Успешный ответ (HTTP 200 OK):**
```json
{
  "short_code": "demo123",
  "target_url": "https://example.com",
  "disabled": false
}
```

### 3.3. Редирект
- **Метод и путь:** `GET /{code}`
- **Активная ссылка:** `307 Temporary Redirect`, заголовок `Location` равен `target_url`, счётчик `clicks` растёт на 1.
- **Отключенная ссылка:** `404 Not Found`, тело `{"detail": "Link disabled"}`, `Location` нет, счётчик не меняется.
- **Несуществующая ссылка:** `404 Not Found`, тело `{"detail": "Link not found"}`.
- Все ответы `POST /links`, `POST /links/{code}/disable` и `POST /links/{code}/enable` содержат `short_code`, `target_url`, `disabled`.

## 4. Нефункциональные требования (NFR)
1. **Безопасность логирования (Zero Auth Leak):** Категорически запрещено логировать сырой заголовок `Authorization`, токены доступа или значение `target_url` в логах сервера.
2. **Транзакционная целостность:** Операция обновления статуса должна фиксироваться в базе данных атомарно (`commit`).
3. **Отсутствие N+1 запросов:** Чтение статуса активности выполняется в том же SQL-запросе, что и получение целевого URL.

## 5. Нерушимые правила слоев
1. **Соблюдение слоев:** Роутеры (`app/main.py`, `app/api/`) не содержат прямого SQL и низкоуровневых операций с транзакциями. Работа с базой ведётся строго через методы `app/repositories/link.py`.
2. **Типизация:** Все аргументы и возвращаемые значения функций строго типизированы (basedpyright strict mode).

## 6. Матрица рисков и Definition of Done (DoD)
- [ ] Поле `disabled` добавлено в модель данных со значением по умолчанию `False`.
- [ ] Реализованы методы `set_active` и `get_by_code` в репозитории.
- [ ] Добавлены хэндлеры `POST /links/{code}/disable` и `POST /links/{code}/enable`.
- [ ] Редирект `GET /{code}` проверяет флаг `disabled` и блокирует переход.
- [ ] Все characterization-тесты Дня 1 зелёные (`pytest tests/flat_api/test_characterization.py`).
- [ ] Тесты активности в `tests/flat_api/test_link_toggle.py` и `tests/flat_api/test_links.py` зелёные.
- [ ] Мутационная проверка `uv run python scripts/mutate_probe.py` завершается с кодом 0 (все мутанты убиты).
- [ ] Миграция Alembic в `alembic/versions/` содержит `disabled` и `clicks` с `server_default`, `env.py` работает с `render_as_batch=True`.
- [ ] Проверка отсутствия дрейфа схемы `uv run alembic upgrade head && uv run alembic check` завершается с кодом 0.
- [ ] Линтер `uv run ruff check app tests` завершается с кодом 0.
- [ ] Тайпчекер `uv run basedpyright` завершается с кодом 0 (0 errors).

## 7. Контрольные точки на диске (Checkpoints)
- Вход: `specs/LINK-42-enable-link.md`
- Пакет сдачи Кодера: `.ai-team/handoff-coder.md`
- Пакет аудита Ревьюера: `.ai-team/handoff-reviewer.md`
- Финальный вердикт Техлид-гейта: `.ai-team/verdict.md`
- Голоса Gate-панели: `.ai-team/panel-votes/*.json` (читает `scripts/generate_proof.py`)
