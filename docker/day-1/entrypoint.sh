#!/usr/bin/env bash
set -e

# Start local PostgreSQL service if available
if command -v service >/dev/null 2>&1; then
    service postgresql start >/dev/null 2>&1 || true
    su - postgres -c "psql -c \"CREATE USER app WITH PASSWORD 'app';\"" >/dev/null 2>&1 || true
    su - postgres -c "psql -c \"CREATE DATABASE app OWNER app;\"" >/dev/null 2>&1 || true
    su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE app TO app;\"" >/dev/null 2>&1 || true
fi

# Ensure /workspace has project files
if [ ! -f /workspace/pyproject.toml ]; then
    echo "Инициализация каталога /workspace из шаблона..."
    cp -r /opt/fastapi-template/. /workspace/
fi

# Apply Mode Configuration
if [ "$MODE" = "no-skills" ]; then
    # VIBE-CODING: Strictly purge all skills, rules, and canon
    rm -rf /workspace/.agents /workspace/.opencode /workspace/AGENTS.md /workspace/CLAUDE.md /workspace/.clinerules 2>/dev/null || true
    rm -f /workspace/opencode.json /workspace/opencode.agentplatform.json.bak 2>/dev/null || true

    cat << 'BANNER'
======================================================================
  ⚠️  РЕЖИМ БЕЗ СКИЛОВ (ЧИСТЫЙ ВАЙБ-КОДИНГ)
======================================================================
  • Скилы удалены (.agents/ нет)
  • Правила удалены (AGENTS.md нет)
  • Никакого канона в окружении нет
  • Агент OpenCode работает вслепую (как обычный чат-бот)

  📁 Папка на хосте Mac: ~/work/pytex-webinar/no-skills
  (все изменения сохраняются на вашем компьютере)

  Для запуска агента введите:
    opencode
  Промпт для показа:
    "Напиши юнит-тест для эндпоинта /api/v1/links"
======================================================================
BANNER

else
    # WITH-SKILLS: Full Engineering Harness
    mkdir -p /workspace/.opencode
    ln -s ../.agents/skills /workspace/.opencode/skills 2>/dev/null || true
    rm -f /workspace/opencode.json /workspace/opencode.agentplatform.json.bak 2>/dev/null || true

    cat << 'BANNER'
======================================================================
  🛡️  РЕЖИМ СО СКИЛАМИ (ИНЖЕНЕРНЫЙ ХАРНЕС)
======================================================================
  • Харнес активен (AGENTS.md на месте)
  • Все 17 скилов AI-SDLC и Дня 1 подключены
  • Автоматический оракул (pytest, ruff, basedpyright)

  📁 Папка на хосте Mac: ~/work/pytex-webinar/with-skills
  (все изменения сохраняются на вашем компьютере)

  Для запуска агента введите:
    opencode
  Промпт для показа:
    "Используй скил tests-unit. Напиши юнит-тест для эндпоинта /api/v1/links"
======================================================================
BANNER
fi

# Ensure .env exists in /workspace
if [ ! -f /workspace/.env ]; then
    cp /workspace/.env.example /workspace/.env
    chmod 600 /workspace/.env
fi

# Ensure virtualenv exists in /workspace
if [ ! -d /workspace/.venv ]; then
    echo "Копирование предварительно собранного .venv..."
    cp -r /opt/base-venv /workspace/.venv
fi

# Run migrations quietly
cd /workspace
uv run alembic upgrade head >/dev/null 2>&1 || true

exec "$@"
