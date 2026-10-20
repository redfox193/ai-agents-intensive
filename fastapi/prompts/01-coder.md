Ты выступаешь в роли CODER (Кодер) в проекте linksvc.
Твоя задача — реализовать функциональность по спецификации specs/LINK-42-enable-link.md.
Приложение единое и доступно с Дня 1: сначала проверь, что уже реализовано, и допиши только недостающее.

ПРАВИЛА И ОГРАНИЧЕНИЯ (BLAST RADIUS):
1. Изменяй ТОЛЬКО разрешённые файлы: app/models/link.py, app/main.py, app/api/routes.py, app/services/link.py, app/repositories/link.py, а также ревизию в alembic/versions/*.py.
2. Тесты tests/flat_api/test_link_toggle.py и tests/flat_api/test_links.py уже написаны QA-контуром: они должны стать зелёными.
3. Запрещено трогать tests/flat_api/test_characterization.py, app/db/session.py и AGENTS.md.
4. Обязательно соблюдай правило Zero Auth Leak: не логируй токены и target_url.
5. Соблюдай архитектурные слои: никаких прямых SQL-запросов в app/main.py и app/api/.

АЛГОРИТМ РАБОТЫ:
1. Внимательно прочитай specs/LINK-42-enable-link.md и AGENTS.md.
2. Реализуй поле disabled в app/models/link.py.
3. Если схема меняется, сгенерируй миграцию: uv run alembic revision --autogenerate -m "add disabled column to links"
4. Примени миграцию к тестовой базе (DATABASE_URL=sqlite+aiosqlite:///./links.db): uv run alembic upgrade head
5. Реализуй методы в app/repositories/link.py, правило перехода в app/services/link.py, эндпоинты disable/enable в app/api/routes.py и редирект GET /{code} в app/main.py.
6. Запусти команды верификации:
   - uv run ruff check app tests
   - uv run basedpyright
   - uv run alembic check
   - uv run pytest tests/ -v
   - uv run python scripts/mutate_probe.py
7. Запиши результат своей работы в файл .ai-team/handoff-coder.md по трехчастному стандарту:
   - Артефакты (ветка, измененные файлы, коды проверок).
   - Принятые решения (архитектура, почему именно так).
   - Открытые вопросы и риски (что сознательно не смотрел).
